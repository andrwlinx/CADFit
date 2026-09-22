# CADFit++ candidate ranking — results

Branch `cadfitpp-candidate-ranking`. All new behaviour is flag-gated and off by
default; with flags off the pipeline reproduces stock output.

## Question

Can a cheap, kernel-free ranker choose which extrusion/revolve candidates reach
CadQuery + boolean-IoU evaluation in `greedy_search.py`, reducing compute without
hurting reconstruction quality?

## Setup

- Machine: Apple Silicon, 12 cores, 6 inner workers, macOS (`spawn` start method,
  so absolute times are slower than the paper's Linux numbers; only same-machine
  ratios are meaningful).
- Data: 30 synthetic CadQuery parts (`bench/make_synthetic.py`, 10 families × 3,
  one tilted variant each) plus 1 real flange. No benchmark meshes were available.
- Baseline: stock `run_pipeline.py --keep-history --max-iterations 1` on all 30
  parts (375 min, 30/30 succeeded, mean IoU 0.91).
- Arms: `greedy_search.py` re-run on the cached analysis of each part so the
  unseeded analysis stage does not add noise. `bench/run_arms.sh`, `bench/compare.py`.

## Where the time goes (stock, 30 parts, 22,522 s)

| phase | share |
|---|---|
| translation analysis | 34% |
| backward removal (pruning) | 29% |
| planar contour extraction | 15% |
| forward greedy | 7% |
| **candidate evaluation (the ranker's target)** | **5%** |
| volume pass (redundant CadQuery rebuilds) | 3% |

Candidates per (type, sketch) group: 615 / 479 = **1.28**. `run_greedy_search`
collapses each group to its best member before pruning, so a diversity-preserving
ranker can remove at most 22% of evaluations — of a 5% phase.

## Ranker quality (offline oracle, `bench/oracle_eval.py`)

Proxy IoU = GT interior samples tested analytically against the candidate solid
(`candidate_ranker.py`), no CAD kernel.

- Proxy vs true IoU: median Spearman 0.981, median abs error 0.0025 (metadata-only
  heuristic from the proposal: 0.880).
- Keep 1 per group: correct pick in 74% of multi-candidate groups; max individual
  regret 0.0087 IoU. Keep 2 per group: 99%.
- Whole-group dropping at proxy < 0.002: 52 of 57 useless groups dropped,
  0 false drops.

## End-to-end (greedy step, 27 parts*)

| arm | wall vs stock | CadQuery launches | same program as stock | mean ΔIoU | worst ΔIoU |
|---|---|---|---|---|---|
| stock | 1.00 | 1264 | 27/27 | — | — |
| `--fast-prune` | **0.76** | 1046 | **27/27** | 0.0000 | 0.0000 |
| ranking (1/group) | 1.11 | 1138 | 26/27 | −0.0077 | **−0.2079** |
| both | 0.90 | 872 | 26/27 | −0.0077 | −0.2079 |

\* three parts excluded where the *stock* arm's wall-clock was inflated 13–15 min.
**Correction (2026-09-22):** this was the laptop sleeping, not a subprocess hang —
the affected `cq_exec` events returned `ok=True`, and the profiles show zero-event
holes across all processes. `subprocess.run` deadlines use `mach_absolute_time`,
which stops during sleep, while the profiler used wall time. The same sleep holes
contaminate the full-pipeline phase shares above (e.g. `l_bracket_2`'s 6392 s
greedy step was ~86% sleep), so those shares are indicative only and are being
re-measured under `caffeinate`. Excluding the three parts keeps the arm comparison
sound because all four arms ran the same 27 parts.

- **Ranking does not pay off.** It costs ~8 s per part (GT point sampling) and
  saves less than that in evaluation. Net slower.
- **Ranking is not safe at 1 per group.** On `pulley_2` it mis-ordered two near-tie
  pairs by < 0.01 individual IoU, but the two intervals are at different heights,
  so the composed program changed and final IoU fell 0.73 → 0.52. Individually
  near-equal candidates are not interchangeable in the composition.
- **`--fast-prune` is a real, lossless win**: it reads each candidate's volume from
  the STL already built during evaluation instead of a fresh CadQuery subprocess,
  and keeps one worker pool across removal iterations. Identical final program on
  27/27 parts, 24% less greedy wall-clock. (A first version reused STLs even when
  the candidate's actions had been swapped by the sketch-index collision below;
  that changed 2 volumes and the greedy path — fixed.)

## Stock CADFit issues found on the way

1. **Sketch-index collision.** Extrusion `sketch_idx` indexes `loops_split.json`,
   revolve `sketch_idx` indexes `loops_split_revolve.json`, but
   `run_greedy_search` merges both into one `sketches_by_idx` entry and hands
   pruning the *winner's* actions for both candidates. The loser is rebuilt from an
   unrelated sketch, so its recorded `individual_iou` does not describe the solid
   greedy builds (`greedy_search.py` ~L765–840).
2. `greedy_extrusion_data.json` `selected` flags and `greedy_keep_mask.json` are
   always False (`cadquery_ops.py` ~L2200).
3. `mesh_iou_cpu_boolean` returns IoU > 1 (1.54 on `boss_on_plate_2`, 1.84 on
   `plate_with_holes_0`). Root cause: two selected extrusions sharing a coplanar
   face are exported as an `.add()` compound; coincident vertices merge on load,
   `body_count` reads 1, the alpha-wrap is skipped, and manifold3d receives a
   self-overlapping mesh (`inter = 1.36 > vol_gt = 0.76`). The `_cached_manifold`
   volume-ratio gate compares the same integral to itself and cannot catch it.
   This corrupts the *search*: forward greedy accepts duplicate/overlapping
   extrusions because the bogus IoU "improves" — `boss_on_plate_2`'s final program
   is the same disc extruded twice. Forcing alpha-wrap on non-watertight or
   winding-inconsistent meshes restores the volume identity (0.86 / 0.76 / 0.93 on
   the affected parts).
4. The 30 s SIGALRM watchdog in `_evaluate_operation_worker` is defeated: its
   `TimeoutError` is swallowed by `except Exception` in `execute_cadquery_script`
   and `compute_iou`, so a stuck task is never abandoned. (The apparent 13–15 min
   "hangs" in this benchmark were laptop sleep, see above.)
5. `run_pipeline.py --alpha` is accepted but never forwarded to `greedy_search.py`.
6. Evaluation timeout message says "4 seconds"; the alarm is 30 s.

## Verdict

The proposed candidate-ranking stage, implemented faithfully with a ranker far
more accurate than the proposal's heuristic, yields no speedup and one quality
regression on this workload. The measured gain over stock CADFit is the lossless
`--fast-prune` arm (0.76× greedy wall-clock). The phases worth targeting next are
backward removal (29%, rebuilds the whole model K times per iteration) and
translation analysis (34%, 401 sweep steps per loop) — neither is touched by
candidate ranking.

## Files

- New: `candidate_ranker.py`, `profiling.py`, `bench/{make_synthetic,oracle_eval,compare,test_proxy}.py`, `bench/run_arms.sh`
- Modified: `greedy_search.py`, `cadquery_ops.py`, `run_pipeline.py`
- Flags: `--candidate-ranking`, `--candidate-per-group`, `--candidate-top-k`,
  `--candidate-keep-ratio`, `--candidate-drop-tau`, `--fast-prune`;
  env `CADFIT_PROFILE=<file>` for per-phase timing events.
- Raw results: `bench/runs/{stock_synth,arms_synth,oracle_synth.json}` (untracked).

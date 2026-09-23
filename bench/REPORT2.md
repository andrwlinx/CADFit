# CADFit++ phase 2 — correctness fixes and lossless speedups

Branch `cadfitpp-candidate-ranking`. Phase 1 (candidate ranking, negative result) is in
`bench/REPORT.md`. Every change below is a flag. After the measurements in §4–5 the proven
ones were made **default-on**; `--no-<flag>` restores stock behaviour for any of them, and
`bench/run_arms.sh stock` reproduces stock exactly (verified: same program, same launch
count). Machine: Apple Silicon 12-core, 6 inner workers.

## 1. Corrections to phase 1

- **The "hangs" were laptop sleep.** `subprocess.run` deadlines use `mach_absolute_time`
  (frozen during sleep) while the profiler used wall time. Phase 1's 375-minute baseline
  was ~75% sleep: re-run under `caffeinate` it takes **91 minutes**.
- **Sleep-free phase shares** (30 parts, 5447 s): forward greedy 25%, translation analysis
  24%, volume pass 13%, backward removal 11%, planar contours 8%, candidate evaluation 6%.
  Pruning as a whole is 49%.
- Benchmarks now run under `caffeinate -dims`, `bench/compare.py` flags runs with dead
  time (sleep or CPU starvation) and excludes them from wall-clock ratios, and quality is
  judged by `bench/score.py`, which alpha-wraps both meshes before the boolean so a metric
  bug cannot flatter any arm.

## 2. Stock CADFit bugs found and fixed (flags)

| bug | effect in stock | fix |
|---|---|---|
| **IoU > 1 on shared-face compounds.** Two selected extrusions that share a coplanar face are exported as an `.add()` compound; coincident vertices merge on load, `body_count` reads 1, the alpha-wrap is skipped, and manifold3d receives a self-overlapping mesh. `_cached_manifold`'s volume-ratio gate compares the same integral with itself and cannot catch it. | Forward greedy accepts duplicate/overlapping extrusions because the bogus IoU "improves" (e.g. the same disc extruded twice); the best-single fallback never fires. | `--fix-iou-validity`: direct conversion only for watertight, winding-consistent, positive-volume meshes; post-check `inter ≤ min(vol)`, `union ≥ max(vol)`, else re-run alpha-wrapped, else score 0. |
| **Sketch identity.** Extrusion `sketch_idx` indexes `loops_split.json`, revolve `sketch_idx` indexes `loops_split_revolve.json`; both are merged under one int and pruning rebuilds the loser from the winner's (unrelated) sketch. Revolves in pruning are also regenerated without the evaluation frame. | Losing candidate's recorded IoU describes a different solid than greedy builds; propagates into `best_greedy_parallel.py`. | `--fix-sketch-identity`: one entry per (type, sketch), each with its own actions, STL and frame. Regression test in `bench/test_fixes.py`. |
| `keep_mask` / `selected` always False (`i < len(final_groups)` guard); cached reload drops `type` so revolves reload as extrusions. | Bookkeeping only. | Fixed unconditionally (`candidate_id`). |
| SIGALRM `TimeoutError` swallowed by `except Exception` — and `cadquery_ops.py` shadows the builtin `TimeoutError` with its own class, so `except TimeoutError` there never matches. | Watchdog never abandons a task; child never killed. | Re-raised; subprocess in its own session, process group killed on timeout. |
| `--alpha` accepted by `run_pipeline.py`, never forwarded. | — | Forwarded. |
| **Unconditional refinement.** Every residual cut/union is applied without checking the result (`run_pipeline.py` cut/union blocks). | Refinement *hurt* 4/30 parts in the stock baseline (flange_0 0.95→0.64, box_with_pocket_0 0.99→0.90) and helped 2. | `--guard-refine`: revert a cut/union if IoU against the ground truth drops. Alone: mean +0.020 (95% CI +0.001..+0.046). |
| 8-entry FIFO manifold cache in `iou.py`. | With alpha-wrapped ground truths the GT is evicted every few candidate evaluations and re-wrapped (7 s each); one refinement pass spent 2307 s re-wrapping. | 64-entry LRU (values unchanged, only recomputation). |

## 3. Lossless speedups (flags)

- `--cache-volumes`: candidate volume from the STL built during evaluation instead of a fresh
  CadQuery subprocess.
- `--persistent-pool`: one worker pool across backward-removal iterations.
- `--cache-solids`: every pruning subset is built by concatenating the evaluated candidate
  STLs instead of re-running CadQuery. A `.add()` compound exports each solid's
  triangulation independently, so the concatenation is triangle-for-triangle identical
  (verified on benchmark parts). Requires `--fix-sketch-identity`.
- `--fast-cd` (translation analysis): `cKDTree(compact_nodes=False)` — scipy's default is
  100–150× slower per query when the surface points are not axis-aligned (tilted parts) —
  plus one tree per sketch and one batched query with per-step means over contiguous
  slices. Output is **byte-identical** (33/33 interval files on three parts); 3.5–4.4×
  faster on tilted parts, neutral on axis-aligned ones. `--seed` added for reproducible
  surface sampling (stock is unseeded).

## 4. Results — greedy step on cached analysis (30 parts, strict judge)

Arms on top of both correctness fixes (`fixed`). "same" = identical final program.

| arm | wall vs fixed* | CadQuery launches | IoU calls | same | strict IoU |
|---|---|---|---|---|---|
| fixed | 1.00 | 1398 | 1049 | 30/30 | 0.9619 |
| + `--cache-volumes` | 0.80 | 1125 | 1049 | 30/30 | 0.9619 |
| + `--persistent-pool` | 1.00 | 1398 | 1049 | 30/30 | 0.9619 |
| + `--cache-solids` | 0.70 | 868 | 1049 | 30/30 | 0.9619 |
| **+ all three** | **0.49** | **595** | 1049 | **30/30** | 0.9619 |

\* ratio over pairs where neither run was slept/starved (all 30 after reruns); the machine
was in interactive use for part of the matrix, so treat wall ratios as ±10%. Launch counts
are deterministic.
With all three caches, pruning makes **zero** CadQuery calls; the 595 that remain are
candidate evaluation. `--persistent-pool` gives no measurable gain on its own.

Correctness fixes vs stock (same 30 parts, strict judge):

| arm | mean strict IoU | worst Δ vs fixed | parts changed |
|---|---|---|---|
| stock | 0.9298 | −0.3057 | 10/30 |
| + `--fix-sketch-identity` only | 0.9298 | −0.3057 | 6/30 |
| + `--fix-iou-validity` only | 0.9619 | −0.0015 | 5/30 |
| both (`fixed`) | **0.9619** | — | — |

`--fix-iou-validity` accounts for the whole gain: five parts where stock's metric steered
greedy into overlapping duplicates go 0.69→0.997, 0.77→0.995, 0.79→0.96, 0.82→0.99,
0.89→0.99; no part regresses. `--fix-sketch-identity` changes what pruning is fed on
6 parts but the final selection ends identical on these synthetic parts (+0.003 on the
real flange). It is kept because it is a correctness precondition for `--cache-solids`.

## 5. Results — full pipeline, 30 parts (stock vs everything on)

`run_pipeline.py --max-iterations 1`, sleep-free (lid open, `caffeinate`), all 30 parts
untainted. Quality by the strict judge on the final reconstruction.

| step | stock | CADFit++ | ratio |
|---|---|---|---|
| greedy search (all passes) | 3447 s | 1678 s | **0.49** |
| translation analysis | 1293 s | 558 s | **0.43** |
| planar contours / revolve / slicing | 652 s | 764 s | 1.17 (untouched; run-to-run noise) |
| **total** | **5447 s** | **3074 s** | **0.56** |

| | stock | CADFit++ |
|---|---|---|
| mean strict IoU | 0.9173 | **0.9726** |
| mean Δ (95% bootstrap CI) | — | **+0.0553** (+0.024..+0.091) |
| parts improved > 0.005 / regressed | — | 10 / 1 (pulley_2 −0.045) |
| largest gains | — | flange_0 +0.31, stepped_block_1 +0.30, stepped_block_0 +0.22, flange_1 +0.17, flange_2 +0.17 |

The one regression is analysis-stage randomness (unseeded surface sampling): pulley_2's
refinement helped by +0.18 in the stock run and by +0.05 here. An intermediate run without
the guard and the LRU cache gave 0.68× / +0.031 with 2 regressions, both traced to the
unguarded refinement.

## 6. What shipped and what is next

Default-on now: `--fix-iou-validity`, `--fix-sketch-identity`, `--guard-refine`,
`--cache-volumes`, `--persistent-pool`, `--cache-solids`, `--fast-cd`. Candidate ranking
stays off (phase 1). On this benchmark CADFit++ is **1.8× faster end to end and +0.055
mean IoU** over stock, with the search producing identical programs wherever only the
caches differ.

Remaining cost centres: candidate evaluation (one interpreter + OCP import per candidate —
a persistent CadQuery worker would remove it), alpha-wrap inside the boolean IoU, and
planar contour extraction. Composition-aware scoring (phase 1's pulley finding) remains
the algorithmic direction.

## Files

- New: `bench/{score,full_compare,test_fixes,rerun_tainted}.py`, `bench/REPORT2.md`,
  `bench/results/phase2/`.
- Modified: `greedy_search.py`, `cadquery_ops.py`, `iou.py`, `analyze_loop_translation.py`,
  `run_pipeline.py`, `bench/{run_arms.sh,compare.py}`.
- Env hooks (set automatically by the flags so pool workers inherit them):
  `CADFIT_IOU_VALIDATE`, `CADFIT_CACHE_SOLIDS`, `CADFIT_FAST_CD`, `CADFIT_PROFILE`.
- Raw comparisons: `bench/results/phase2/{arms2_summary,arms2_scores,full_compare_full_all2,full_compare_full_guard}.json`.

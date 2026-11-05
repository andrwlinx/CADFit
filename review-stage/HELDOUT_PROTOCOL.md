# Held-out pipeline evaluation protocol (fresh2) — frozen before any fresh2 outcome is seen

Submission: bench/h2_submit.sh (freezes every arm, then submits). Status: proposed for reviewer approval (run run_20261026_b59bde60, round 3). No fresh2 reconstruction,
score or timing has been produced or inspected. The 300 STLs are on disk (needed to run); nothing derived
from them beyond the manifest checks in review round 1 (count, split balance, disjointness) and the
watertightness check in round 2 (26 of 300 GTs are open) has been looked at.

## Cohort
- bench/cadbench/fresh2: 300 parts, 150 benchA-hard + 150 benchE-hard (CADBench), disjoint from every other
  set on disk (review round 1 verified, including by source-part prefix).
- Every part is in every denominator. A part an arm leaves without a model scores 0 (validity-gated).

## Source freeze
- One commit C (the commit that adds this file and bench/h2_submit.sh). Every arm runs from a full
  `git archive` of its source (bench/ replay and judge code included), created before submission:
  - d0: `git archive e260397` + bench/d0_infra.patch (infrastructure only: decimation memory bound, CadQuery
    worker retry; same as dev5 d0) + bench/d0_seed.patch (common experimental control: revolve-axis surface
    sampling seeded by CADFIT_SEED, as in every other arm; e260397's sampler ignored the seed). No method change.
  - dx, v2, v3: `git archive C`.
- The runner (bench/run_parallel_arms.sh: arm flags, environment) runs from the frozen tree too
  (RUNNER_SRC=bench/runs/h2_src, set by bench/h2_submit.sh); job scripts are copied by sbatch at submission.
- Every post-processing step runs from the frozen tree `bench/runs/h2_src` = `git archive C`, by
  bench/h2_post.sh, in this order: score (bench/score.py --cad, robust judge as of f708bb2) → trim on each
  v3 run (bench/analysis/trim_posthoc.py = exec_verify trim stage; records the selected program/STL) →
  section (bench/section_control.py) → rejudge (bench/rejudge.py, on the delivered artifacts including the
  selected trim variants) → surface (bench/detail_scores.py, fused-boundary definition, selected trim
  artifacts via --trim) → timing (bench/analysis/timing_export.py) → stats (bench/analysis/v2_dev.py with
  --manifest fresh2: refuses to analyse a run lacking a record for any of the 300 parts).

## Arms (bench/run_parallel_arms.sh flags at C)
| Arm | Definition | Runs |
|---|---|---|
| d0 | pre-v2 beamsec pipeline (+ infra and seeding-control patches) | SEED 0 |
| dx | d0 flags + execution-verified delivery (exec-verify) | SEED 0 |
| v2 | dx + original-mesh sections/scoring + shared geometry fixes | SEED 0, 1, 2 |
| v3 | v2 + precise extents (part-extent sweep, finer grid on thin directions, ends snapped to cap planes, grid-end alternative kept) | SEED 0, 1, 2 |
| v3+trim | each v3 run's delivered program + silhouette-trim variant (exec_verify trim stage, post hoc on the saved deliveries; its added time measured) | derived from each v3 run |
| section-only | best whole-part section extrusion, executed and validity-checked (bench/section_control.py) | deterministic |

Rationale for repeats: dx−d0 and v2−d0 are large (dev: +0.10/+0.11); v3−v2 and trim are small (dev:
+0.009, +0.005) and need repeats. d0 and dx are single-run references: v2−dx compares a 3-run part mean with
one dx run, which is unbiased but is not a matched-seed replicated contrast. For repeated arms both per-run
validity rates and "valid in every repeat" are reported.

## Resources and retry policy (identical for every arm)
- Slurm job: 48 CPUs, 180 GB, 12 chunks of 25 parts per run (bench/h2_submit.sh), JOBS=3 parts at a time per job (CADFIT_MAX_PARALLEL=3,
  inner workers ~nproc/3); partitions mit_normal + mit_preemptable with requeue (parts are resumable:
  a part with final_iou.json is skipped; a requeued part restarts from scratch); preemptable nodes
  node1700–1705, 1708–1709, 1800–1805 excluded (node1701 and node1801 observed without /orcd/software; the
  list is exactly bench/h2_submit.sh's EXCL). Infrastructure amendment after launch (2026-11-01 17:30): the
  failing nodes are those tagged `ubuntu24` (node2801 also), so jobs require `--constraint=rocky8`; two
  h2s1 chunks (4, 5) had exited at start on node2801 without running any part and were resubmitted with the
  constraint (job 27590010). No part had started; no method or analysis change.
- A chunk that is OOM-killed is rerun once with JOBS=2; a part still without a model after that scores 0.
  The same rule applies to every arm. Number of reruns and of parts affected is reported per arm.
- Timing (bench/analysis/timing_export.py, keyed by run and part): successful-attempt wall time
  (final_iou.json duration), number of attempts (job logs; retried attempts' time is not in it), the
  concurrency of the delivering job, and the trim stage's seconds. Reported as successful-attempt deployment
  latency under this configuration, not total compute and not an algorithmic speed comparison.

## Metrics
- Primary: validity-gated CAD IoU (score.py --cad: program replayed in a fresh process, OCC validity of the
  shape and every solid, judged by robust_iou), mean over all 300 parts.
- Also reported: valid deliveries, failure types (no model / does not build / invalid), mesh IoU, the two
  splits separately and their balanced average.
- Surface agreement (diagnostic, secondary): recall/precision/F at tau 0.25/0.5/1/2% of part size against the
  fused occupied boundary, exact distances, gated; common-valid subsets reported as diagnostic only.
- Small differences (|mean diff| < 0.01) are re-checked with bench/rejudge.py: every part judged by the
  Monte Carlo estimate is judged again on the same executed STL with an independent seed and 4x the union
  samples (exact-judged parts have no sampling error); selection decisions fixed.

## Contrasts and statistics (prespecified)
- Primary contrast: dx − d0 (reliability of execution-verified delivery), analysed alone.
- Secondary confirmatory family (exactly these four): v2 − dx, v3 − v2, (v3+trim) − v3, (v3+trim) −
  section-only. Other comparisons with section-only are descriptive.
- Repeats are averaged within part before comparison (v2, v3, v3+trim: mean of 3 runs per part). Parts are the
  resampling unit; bootstrap within split (10,000 resamples, seed 0), reporting the balanced-split mean
  difference and its 95% percentile interval (nominal). Two-sided paired sign tests with Holm correction over
  the 4 secondary contrasts; the Holm correction applies to the sign tests, not to the intervals.
- Validity changes reported as paired counts (valid in a / valid in b).
- No part-level selection of best runs. No exclusion after the fact.

## Reserved before any fresh2 outcome (GPU studies, run later)
- bench/cadbench/fresh2_subset.json (bench/fresh2_subset.py): 20 benchA + 20 benchE parts drawn from the
  manifest alone with random.Random(20261101). The LLM agent study on fresh2 (corrected harness: code,
  code+section, skills, matched scripted policy; Gemma-4-31B; 3 episodes per condition, clustered by part)
  and the CADFather comparison (common judge, bench/cadfather_adapt.py) use exactly these 40 parts.
- Opus/Sonnet — deferred by the user; if added, on the same 40 parts.

## Measurement notes
- Surface agreement uses the OCC-fused boundary; a part whose solids do not fuse uses the winding-number
  approximation and is flagged (`boundary: winding`) in the output and reported as such.

## Amendments after outcomes existed (2026-11-05)
- **Replay-failure recovery (post-outcome measurement amendment to frozen generation; dated 2026-11-05,
  decided after the affected score files existed, so not preregistered).** The per-part score cache
  (h2_src_c) stored replay failures that were never a usable evaluation: h2s0_dx 299/300 "ns_sandbox:
  could not make read-only" (sandbox setup on one node), h2s2_v2 222 "timeout 900s" (seeds 0/1 of v2 had
  none), h2s0_d0 7 rc -9 kills + 3 timeouts. Classes (`score.env_failure`): *setup* = the sandbox could
  not be set up (no evaluation took place); *resource* = rc -9 kill or the 900 s timeout, which may be
  the machine or the program and is called a resource-limit failure, not a proven machine fault.
  Rule, identical for all 8 runs: the eligible list is frozen from the original score files
  (kept as h2_scores_<run>.pre_recovery.json; list in bench/runs/h2_env_cleared.json); each listed part
  gets **one** recovery scoring pass from h2_src_c3 (= h2_src_c2 + this rule) with the same judge, the
  same 900 s limit and the scorer's existing single retry of a silent replay death, at fixed
  concurrency JOBS=4 on mit_preemptable rocky8 nodes; the recovery result is cached and terminal
  (h2_env_clear.py refuses a second pass). A recovery that fails again scores 0 in the gated metric,
  and its cause is reported separately from geometric invalidity. Programs are not regenerated and no
  search or selection is redone. Both the original and the recovered analyses are reported, whatever
  their significance.
- **Trim records not recovered.** The trim run's own replay failures stay as frozen (e.g. seed 0
  00403399: valid v3 delivery 0.9307, trim record "timeout 600s", scored 0). The final-package-vs-v3
  contrast is reported as preregistered, with a diagnostic split into the second fuse/repair pass
  (`gated_no_trim`) and the trim proper, and the full added wall time.
- **Closed models.** Claude Opus 5.5 and Sonnet 5.5 ran on the 40 reserved parts (one episode each,
  code and skills toolsets, effort high, same budget); exploratory, compared per part with the pipeline
  in bench/analysis/closed_vs_pipeline.py. A first Opus run on node4002 (every executed call timed out
  at 90 s) was set aside as agentsk_f2/opus55_node4002_failed and rerun; bench/claude_job.sh now builds
  one CadQuery box before any API call.

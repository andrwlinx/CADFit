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
    worker retry; same as dev5 d0).
  - dx, v2, v3: `git archive C`.
- Scoring (bench/score.py --cad, robust judge as of f708bb2), trim (bench/analysis/trim_posthoc.py =
  exec_verify trim stage), section control (bench/section_control.py), surface agreement
  (bench/detail_scores.py, fused-boundary definition of 88564a5 + 2539f16) all run from `git archive C`.

## Arms (bench/run_parallel_arms.sh flags at C)
| Arm | Definition | Runs |
|---|---|---|
| d0 | pre-v2 beamsec pipeline (+ infra patch) | SEED 0 |
| dx | d0 flags + execution-verified delivery (exec-verify) | SEED 0 |
| v2 | dx + original-mesh sections/scoring + shared geometry fixes | SEED 0, 1, 2 |
| v3 | v2 + precise extents (part-extent sweep, finer grid on thin directions, ends snapped to cap planes, grid-end alternative kept) | SEED 0, 1, 2 |
| v3+trim | each v3 run's delivered program + silhouette-trim variant (exec_verify trim stage, post hoc on the saved deliveries; its added time measured) | derived from each v3 run |
| section-only | best whole-part section extrusion, executed and validity-checked (bench/section_control.py) | deterministic |

Rationale for repeats: dx−d0 and v2−d0 are large (dev: +0.10/+0.11); v2−dx, v3−v2 and trim are small
(dev: +0.012, +0.009, +0.005) and need repeats; d0/dx single runs (dev run-to-run spread of v2 across 4 runs:
0.9485–0.9564 on the mean).

## Resources and retry policy (identical for every arm)
- Slurm job: 48 CPUs, 180 GB, 12 chunks of 25 parts per run (bench/h2_submit.sh), JOBS=3 parts at a time per job (CADFIT_MAX_PARALLEL=3,
  inner workers ~nproc/3); partitions mit_normal + mit_preemptable with requeue (parts are resumable:
  a part with final_iou.json is skipped; a requeued part restarts from scratch); nodes 1700–1709, 1800–1805
  excluded (no /orcd/software).
- A chunk that is OOM-killed is rerun once with JOBS=2; a part still without a model after that scores 0.
  The same rule applies to every arm. Number of reruns and of parts affected is reported per arm.
- Per-part wall time is recorded (final_iou.json duration; CADFIT_PROFILE stage events). Concurrency (3 or 2
  parts per 48-core node) is recorded per part from the job logs. Time is reported as deployment latency
  under this configuration, not as an algorithmic speed comparison.

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
- Primary contrast: dx − d0 (reliability of execution-verified delivery).
- Secondary: v2 − dx, v3 − v2, (v3+trim) − v3, and each arm vs section-only.
- Repeats are averaged within part before comparison (v2, v3, v3+trim: mean of 3 runs per part). Parts are the
  resampling unit; bootstrap within split (10,000 resamples, seed 0), reporting the balanced-split mean
  difference and its 95% percentile interval. Two-sided paired sign tests with Holm correction over the 4
  secondary contrasts; the Holm correction applies to the sign tests, not to the intervals.
- Validity changes reported as paired counts (valid in a / valid in b).
- No part-level selection of best runs. No exclusion after the fact.

## Not part of this freeze
- LLM agent study on fresh2 (subset, models, episodes) — separate decision, prespecified before its launch.
- CADFather comparison on fresh2 — subset fixed before any pipeline fresh2 outcome is inspected (if run).
- Opus/Sonnet — deferred by the user.

# CADFit++ research review — 2026-10-14

Reviewer: Codex gpt-6-astra (ultra reasoning), via `/aris:research-review`. 2 rounds.
Thread `01a13934-b637-7593-9656-6b4e23834789`. Briefs: `RESEARCH_REVIEW_REQUEST.md`,
`RESEARCH_REVIEW_ROUND_2.md`. Traces: `.aris/traces/research-review/2026-10-14_run01/`.

**Verdict:** this is not ready for NeurIPS/ICML. The current numbers have measurement defects. A trivial
geometric control beats the LLM agent, and CADFather (arXiv 2610.09127, 2026-10-06) already
covers the agent idea. A workshop paper (CAD/geometry or ML-for-design) is realistic once
measurement is fixed and a fresh cohort is run.

## 1. Findings (round 1)

Codex verified each of these by running probes against the saved artifacts.

| # | Finding | Evidence | Status |
|---|---|---|---|
| 1 | **The judge fills internal cavities.** `iou._bodies_union_manifold` (iou.py:225) unions all split bodies, including negative-volume cavity shells. The pipeline uses the same helper, so the two don't independently check each other. | 00344388 beam: 0.9758 → 0.9862 with cavities kept. 00014841 rules: 0.9102 → 0.9475 | Accepted. The helper was confirmed by reading it. Not yet fixed. |
| 2 | **A "valid" score doesn't mean valid CAD.** Under `--exact-union` the scored mesh comes from manifold booleans. The combined CadQuery program isn't executed, and `score.py` marks the part valid. | p3test2_beam 00706786 scores 0.980, but its shape fails `isValid()`. 00409618 has 2 of 33 solids invalid. | Accepted |
| 3 | **A trivial control beats the agent.** For each axis, take the target's mid-section, simplify it with the `section` tool, and extrude it through the target's extent. Keep whichever is best by the agent's evaluator. | Pipeline 0.6264; agent mean of 3 runs 0.6998; agent best of 3 runs 0.7363; control **0.7483**. 00182325: control 0.9957 vs agent 0.9199. 00875997: control equals the agent's score exactly. These two parts account for 74.5% of the agent's gain. The control was designed after seeing the results. | Accepted |
| 4 | **The CADBench headline is mislabeled.** 0.8445 is the phase-2 base, not upstream stock CADFit, and the arms used different code snapshots. Rescuing 2 parts that failed before the search accounts for 32% of the base→beam gain. | Same-code dev: beam alone 0.8543 → 0.8589, +0.0047, CI about [0.0013, 0.0086] | Accepted |
| 5 | **The agent's budget isn't enforced.** The deadline is checked only before a request, and tool calls still run after it. 26 of 30 refine runs went over 20 min (max 25.1). The 00479221 "win" is just re-exporting the pipeline model, which switches the judge from Monte Carlo to exact scoring. | agent_loop.py:195 | Accepted |
| 6 | **The ABC soup judge has errors.** It samples only `[-1.05,1.05]³`, so a reconstruction outside that box gets clipped (abc60c beam 00000156 is flagged). Thin parts have too few occupied samples: abc40 00001081 has SE about 0.04–0.05, which is too coarse for the 0.01 win threshold. The judge also uses the repair's own GWN code. | abc60cr_pscores.json | Accepted |
| 7 | **There is no untouched test set.** REPORT3 analysed test geometry, the agent loop was tuned on the 10 weakest test parts, and abc60 was reused while fixing bugs. On CADBench, 23 of 100 test scores are Monte Carlo and 16 targets aren't watertight. The ±0.021 is the SD of 3 run means, not uncertainty over shapes. | — | Accepted |

**What Codex found correct:** the headline arithmetic, the abc60 merge (60 parts, matches the
source files), failures counting as 0, skipping repair on watertight parts, the gwn_repair
cavity fix, and the agent's best-model retention under its own objective.

## 2. What can be claimed today

| Line of work | Defensible claim |
|---|---|
| Search engineering | Engineering changes improve mesh quality and reliability on these development sets. Same-code evidence shows a modest beam gain (+0.005). |
| GWN repair | abc60 0.663 → 0.725, measured against GWN-defined occupancy on a reused set. Recovering the true volume isn't shown. |
| Agent | Improves some pipeline failures. Being better than cheap deterministic geometry is **not** supported. |

## 3. Consensus (round 2)

- Reframe the agent's wins as **"the pipeline lacks reliable full-span extrusion proposals"**.
  That is a pipeline fix. The pipeline already makes single extrusions and has a best-single
  fallback, but on 00182325 the extrusion parameters are wrong.
- **Drop the agent as a headline contribution.** It stays only as a conditional study on
  residual-hard parts, compared against equal-time search.
- **Story:** "Correct measurement and simple geometric proposals explain apparent gains from
  CAD agents" (conditional on the fresh results). **Venue:** a workshop.

## 4. Results-to-claims matrix

| Stage | Claim it can support | Requirements |
|---|---|---|
| Corrected judge + executed final programs | Fidelity numbers correspond to valid, replayable CAD | Keep cavities; soup bounds that cover both shapes; MC convergence; a defined target solid for non-watertight GT |
| Same-code A → B | The whole rules package helps (not individual rules) | Same preprocessing, seeds, judge |
| Same-code B → C | Beam's incremental benefit | Identical candidates, budgets, scoring |
| C → D (+ section proposals) | This proposal family helps on fresh parts | Also report "best of C and sections" standalone. Adding candidates can change the search path. |
| Agent on gated residual-hard parts | Conditional gain beyond strengthened geometry | Gate fixed in advance, equal-time search control, 2 repeats (report the mean, not best-of), eligible fraction |

## 5. TODO, in order

1. **Fix measurement on existing artifacts** (no fresh compute; about 1 day of work, scoring
   CPU-hours).
   - Keep cavity shells in `_bodies_union_manifold`, then rescore everything.
   - `score.py`: execute the final CadQuery program, check `isValid()`, and judge the
     regenerated geometry. Report mesh fidelity and CAD validity separately.
   - Soup judge: compute bounds covering GT ∪ recon. Add a convergence check (more samples for
     thin parts).
   - Agent: enforce the deadline after tool calls. Add a no-op re-export control.
   - Pull the missing agent trajectories and reconstructions from the workstation.
   - Freeze the section-extrusion recipe and the agent eligibility gate (e.g. strengthened
     pipeline IoU < 0.90) on dev data.
2. **Fresh cohort:** 60 never-inspected parts (30 benchA-hard + 30 benchE-hard). Explicitly
   exclude every ID seen before, using an empty input dir. `fetch_cadbench.py:71` only
   excludes IDs from its own call, so it needs an exclusion list.
3. **Four arms, one code version,** `--seed 0 --max-iterations 1`, 5 parts at once,
   `CADFIT_INNER_WORKERS=15`. 240 runs ≈ **12–16 h** plus scoring and replay.
   - A: corrected base
   - B: `--persistent-cq --exact-union --cut-phase --event-slices --detect-directions --translation-max-points 400`
   - C: B + `--beam 4`
   - D: C + the 3 section-extrusion proposals
   - Plus the standalone "best of C and sections" control.
4. **Agent study (optional):** apply the gate to the fresh cohort and take at most 20 eligible
   parts, chosen at random. Compare 3 conditions from the same starting artifacts: C as is;
   C + 1200 s more geometric search; Qwen3.8-27B refine with 40 calls and an enforced 1200 s,
   2 repeats. About **13.3 GPU-h**. Don't reuse the `ms` arm, because it enables loft/sweep.
5. **GWN repair:** keep it separate unless it becomes the main claim. If so, validate on clean
   CAD with faces removed on purpose (known closed GT) plus fresh soups.

**Disk** (16 GB free): `run_parallel_arms.sh` needs 80 GB free by default, so set the limit
after a pilot. Agent prep keeps 9.45 GiB, but what the agent uses is about 116 MB. Keep the
final CAD, meshes, scores, configs, logs and trajectories, and delete bulky intermediates.

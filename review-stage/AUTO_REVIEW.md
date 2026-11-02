# Auto review loop — CADFit++ (run_20261014_49c46147)

Started 2026-10-14. Reviewer: Codex gpt-6-astra, thread 01a13934-b637-7593-9656-6b4e23834789
(continues the /aris:research-review thread; rounds 1–2 = RESEARCH_REVIEW.md).
Reviewer raw responses: review-stage/REVIEWER_MEMORY.md. Difficulty: medium.

## Rounds 1–2 (2026-10-14 03:00–03:20)

### Assessment (Summary)
- Score: not given; verdict: not ready (reject for NeurIPS/ICML; workshop plausible after fixes)
- Key criticisms: judge fills cavities; exact-union scores are not checked as executable CAD;
  mid-section extrusion control beats the agent; CADBench headline mislabeled (failure rescue,
  not beam); agent deadline not enforced; soup judge clips at ±1.05 and is imprecise on
  thin parts; no untouched test set; CADFather pre-empts the agent idea.

### Reviewer Raw Response
See REVIEWER_MEMORY.md, Rounds 1 and 2 (verbatim).

### Actions Taken (Phase C, 2026-10-14 03:30–11:10)
1. `iou._bodies_union_manifold`: inward-facing bodies (negative signed volume) are now
   flipped and subtracted. Reproduces the reviewer's values exactly: 00344388 0.9758 → 0.9862,
   00014841 0.9102 → 0.9475.
2. `bench/cad_replay.py` + `score.py --cad`: runs each final CadQuery program in a fresh
   process, checks OCC validity of the shape and every solid, tessellates it, and judges the rebuilt
   geometry (`iou_cad`, `cad_built`, `cad_valid`). Confirms 00706786 (1/4 solids invalid) and
   00409618 (2/33). New finding: the beam program for 00014841 does not build at all
   (`Null TopoDS_Shape` in a cut of the combined program).
3. Soup judge: samples in the GT's bounding box (padded 1%), counts reconstruction material
   outside that box at the same density (no clipping), and adds 100k-point chunks until the
   union holds ≥10,000 samples or 1M points. Reports `se`.
4. Agent loop: the deadline now bounds every request (HTTP timeout = time left), retries, and
   tool execution. Tool calls returned after the deadline are not run (`stop = 'time'`).
5. `section_extrude.py` (frozen recipe: mid-bbox section per axis, simplify 0.002, extrude
   through the full extent) + `--section-extrude` = arm D. These are generic candidates in the greedy
   pool. Bug found in the smoke test: the loft twist check (alpha-wrap/mesh volume > 1.12)
   rejected every section extrusion with pockets, so they are now exempt. After the fix, 00182325 → 0.9958 and
   00875997 → 0.9316, both CAD-valid (these are test parts, so this is a smoke check only).
6. `agent/search_baseline.py`: equal-time scripted search (best-improvement add/cut/remove
   over the same candidate pool and workspace as the agent, same budget including pool load).
7. `bench/section_control.py`: standalone pipeline / best section / best-of control.
8. Fresh cohort `bench/cadbench/fresh`: 30 benchA-hard + 30 benchE-hard, selected after
   all earlier sets and excluding every file_id already on disk (0 overlap with
   test/dev/smoke/beamfix5).
9. `bench/overnight.sh` on the workstation (launched 11:07): arm C (`beamkh` = beam +
   `--keep-history`, pools pruned to what the agent reads) → gated agent study
   (`bench/agent_study.sh`: judge IoU < 0.90, ≤20 parts with seed 0; pipeline vs equal-time search
   vs Qwen3.8 refine ×2) in parallel with arms A (base), B (rules), D (beamsec) → scoring
   with `--cad` → section control.

### Status
- Waiting for the overnight run; then round 3 review.

---

# Auto review loop — CADFit++ v2 (run_20261018_3f681321)

Started 2026-10-18. Reviewer: Codex gpt-6-astra xhigh, thread 01a151f6-8b58-76b3-98d6-c0f67e4a1e69 (fresh thread;
backend probe: Copilot-native unbound → codex). Goal set by the user: improve the system and tools (mesh-vs-CAD gap,
IoU(CAD) of pipeline D and of agents, agent toolset), evaluate on a new held-out cohort. Difficulty: medium.
Previous run run_20261014_49c46147 was stale (>24 h, in_progress) and is archived as REVIEW_STATE.run_20261014_49c46147.stale.json.

## Round 1 (2026-10-18 04:10)

### Assessment (Summary)
- Score: 4/10
- Verdict: not ready
- Key criticisms: (1) executability is outside the acceptance criterion (search scores mesh unions, program composes
  `.add()` compounds); (2) decimation corrupts thin parts and feeds section proposals (00729452: D 0.281 vs section
  control 0.982); (3) revolve axis omits the plane origin; small profiles (<1e-3) dropped; nesting/densify fixes only
  in skills; (4) tools give no feedback on the assembled program; (5) harness: nudges never reset, deadline not
  enforced inside tools, matched-policy economy differs; (6) controls pending; CADFather already does
  execution-aware selection, so contribution must be diagnosis + repair + controlled result.

### Reviewer Raw Response
Verbatim in review-stage/REVIEWER_MEMORY.md, "run_20261018_3f681321 / Round 1".

### Actions Taken (Phase C)
- Local repro (Mac, current code, arm D flags) of fresh failures: 00090768 → original program builds 133 overlapping
  solids (1 invalid), IoU(CAD) 0.995 locally (ORCD frozen run: valid, 0.002 — not reproduced; ORCD artifacts needed);
  00642725 → original program fails `Standard_Failure: NCollection_Sequence::ChangeValue` (matches ORCD D record);
  00983172 builds locally.
- `exec_verify.py` + `run_pipeline.py --exec-verify` (A-043). On the repros: 00090768 fused = 1 valid solid, 0.9997
  (vs original invalid 0.995); 00642725 fused = valid 0.9345 (original does not build; mesh 0.936).
- `--section-original`, `--score-original` (A-044).
- Revolve axis origin fix, default on, with a translated-shaft regression test that fails on stock (A-045).
- `--shared-fixes`: even-odd nesting in split_loops, min loop area 1e-4, revolve split densify (A-046).
- Agent tools v2 (`CADFIT_AGENT_EXEC=1`): executed-program feedback in add/cut/remove/evaluate, best executed valid
  program as answer, build-failure reasons in fit tools, verified revolve-axis hints (A-047); harness v2: nudge reset,
  deadline enforced inside tools (A-048). Scripted end-to-end test passes; exported program replays valid.
- New held-out cohort fresh2 (300 parts) defined and downloading, verified disjoint from all on-disk sets (A-049).
- tests/test_agent_skills.py: 16 passed (incl. the new offset-shaft test).

### Status
- Pending: dev check of v2 arm on fresh (local), held-out runs (ORCD, needs `ssh -fN orcd`).

---

# Auto review loop — CADFit++ v2, continued (run_20261019_e1c2d949)

Started 2026-10-19 13:10. Previous run run_20261018_3f681321 was stale (state timestamp > 24 h) and is archived as
REVIEW_STATE.run_20261018_3f681321.stale.json. Backend probe: Copilot-native challenge exit 3 (no Copilot root
session) → codex. Reviewer: Codex gpt-6-astra xhigh, fresh thread 01a15522-2119-7033-b0b4-d4a27983fd3f, given
review-stage/REVIEWER_MEMORY.md as its memory. Goal (user): more research, further improve the system and tools.
Difficulty: medium.

## Round 1 (2026-10-19 13:15)

### Assessment (Summary)
- Score: 4/10
- Verdict: not ready (hold the held-out evaluation)
- Key criticisms: (1) tools-v2 exec cache keyed by id() returns a removed step's record; answer metadata from
  ws.best; (2) exec_verify prefers an invalid program that beats the best valid one by > 0.005, and a failed
  verification leaves the unverified output; (3) deadline: TimeoutError swallowed by `except Exception` in
  geometry stages, candidate subprocess survives, policy has no in-tool deadline and accepts on mesh IoU;
  (4) revolve crossing check ignores circle radii / arc extrema (00941601 refine sketch 9); (5) agentsk_score
  hard-codes fresh references (KeyError on fresh2), score.py drops never-started parts, freeze covers only
  top-level modules; (6) no early valid incumbent; refinement acceptance on the decimated mesh; attribution
  controls and an unsupported "skills not planning" inference.

### Reviewer Raw Response
Verbatim: review-stage/ROUND1_run_20261019_e1c2d949.response.md (also appended to REVIEWER_MEMORY.md);
trace .aris/traces/auto-review-loop/2026-10-19_run01/001-round-1-review.

### Research (parallel)
Literature scan review-stage/LIT_SCAN_2026-10-19.md (37 arXiv IDs verified): CADFather (2610.09127) already has
execution-aware selection with per-call executed feedback and original-mesh sections; what remains ours is OCC
BRep-level validity and *repair* (fused rewrite) instead of discarding, plus the matched-budget tool/policy study.
Top cheap ideas: repair ladder before discarding (ShapeFix → fuzzy booleans → fused), axis fit from normals,
local edits on the delivered program, thin-wall handling.

### Actions Taken (commit e72cc73; ledger A-051..A-059)
1. exec cache keyed by program text; answer metadata from the delivered program (agents, policy).
2. exec_verify: best valid program always; best built only if none valid (`chosen_valid`, `validity_gated_iou`);
   failed verification recorded `delivered_unverified`, gated 0; fallback pool + top-3 singles + best section.
3. `cad_tools.run_until` / `SessionTimeout(BaseException)`; candidate process group killed on any interruption;
   4 bare excepts in geometry narrowed; policy uses the same deadline, reserves 5 min for assembly, and under
   tools v2 accepts a trial only on executed-IoU gain of a valid program.
4. Revolve: emitted curves sampled (arcs, circles, splines); crossing ≤ 2e-4 → axis moved; larger → candidate
   fails with a reason. New: fit_revolve takes a given in-plane axis (tools v2) — an oblique shaft got no
   candidate before.
5. Degenerate three-point arcs emitted as lines (--shared-fixes / tools v2): 2 real dev failures verified collinear.
6. Refinement acceptance/volume ratios on the original mesh under --score-original.
7. Evaluation: full git-archive freezes per arm / agents / policy / scoring; agentsk_score references
   parametrized; score.py counts never-started parts (`not_run`) and reports gated IoU(CAD) + judge info;
   submit plan adds code/codesec v2 controls; skills v1 vs v2 labelled a package comparison.
8. NARRATIVE_REPORT: removed the "skills, not planning" inference.

### Results
- tests: 27 passed (16 old + 11 new regressions: cache add/remove/add, valid-first choose, timeout through
  `except Exception`, circle/arc crossing rejection, on-axis profile builds, rotated+translated shaft, collinear arc).
- smoke (00589302, v2 flags + exec-verify): delivered 'original' valid 0.9484; revolve: 6 candidates rejected
  with a reason (previously 11 opaque BRep failures).
- policy smoke (tools v2, 3 min): deadline hit at the limit inside a tool call; assembly still delivered a valid
  executed 0.974.
- Dev diagnosis (local, HEAD a299bef): candidate build failures on 11 dev2 parts — 32/46 revolve
  (BRep_API, mostly junk: 1e-4 circles, discs about tangent axes), 6/46 degenerate arcs.
- ORCD dev3 (a299bef, d0/dx/v2 on fresh, job 26375744): running; partial.

### Status
- Continuing to round 2 (code review of the fixes) while dev3 runs; dev4 (dx/v2 at e72cc73) once ORCD is reachable.

## Round 2 — REVIEW_UNAVAILABLE (2026-10-19 ~15:00)

The round-2 Codex call (thread 01a15522-…) failed: "You've hit your usage limit … try again at Oct 24th, 2026
5:05 PM." No other cross-family reviewer is configured (manual/oracle/agy absent; Copilot-native unbound), so no
round-2 verdict exists. The loop is paused at round 1 (4/10, not ready); fixes in e72cc73 are unreviewed.

### Experiments while the reviewer is unavailable (user: keep experimenting, hold fresh2)
- dev3 (a299bef; d0/dx/v2 on fresh, ORCD 26375744), partial 35/60: the old margin rule delivered an invalid program on
  2 parts where a valid one existed (00232213: invalid 0.8725 over fused valid 0.8609; 00365747: invalid 0.9556
  over single valid 0.8936) — the round-1 finding 2, observed.
- 4af3aa8: ShapeFix repair pass (A-060); 00232213 → `original_repair` valid 0.8725.
- dev4 (4af3aa8; dx/v2 on fresh, ORCD 26392902) queued; scoring of dev3+dev4 with --cad from the frozen 4af3aa8
  tree (26392922, after both) → bench/runs/dev34_scores.json.

### Dev-cohort results: dev3 (a299bef) vs dev4 (4af3aa8), scored 2026-10-20 (job 26392922)

`bench/runs/dev34_scores.json`. 60 dev parts (cohort `fresh`), every run scores all 60; a missing model counts as 0. Metric: validity-gated IoU(CAD). Paired bootstrap over parts (10k resamples); wins and losses count parts that differ by more than 0.005.

| run | mean IoU(mesh) | mean IoU(CAD) | gated IoU(CAD) | invalid or unbuilt |
|---|---|---|---|---|
| dev3_d0 | 0.9048 | 0.8540 | 0.8080 | 8 |
| dev3_dx | 0.9203 | 0.9202 | 0.8898 | 4 |
| dev3_v2 | 0.9267 | 0.9267 | 0.9122 | 3 |
| dev4_dx | 0.9200 | 0.9200 | 0.9200 | 2 |
| dev4_v2 | 0.9489 | 0.9489 | 0.9489 | 1 |

| contrast | Δ gated | 95% CI | wins/losses |
|---|---|---|---|
| dev4_v2 − dev3_d0 | +0.141 | [+0.062, +0.233] | 13/2 |
| dev4_dx − dev3_d0 | +0.112 | [+0.045, +0.193] | 9/0 |
| dev4_v2 − dev4_dx | +0.029 | [−0.002, +0.074] | 8/3 |
| dev4_v2 − dev3_v2 (round-1 fixes) | +0.037 | [+0.001, +0.086] | 5/0 |
| dev4_dx − dev3_dx | +0.030 | [−0.032, +0.094] | 4/1 |

- In dev4 the IoU(CAD) and gated means are equal. Every built delivery was valid; the only zeros come from parts with no model. In dev3, invalid programs were delivered on 00232213 (dx and v2) and 00365747 (dx). With the valid-first choice plus the repair pass, dev4 delivers valid programs for both (00232213 is now 0.873 from `original_repair`).
- Remaining zeros:
  - 00247424 in every arm: OOM kill, exit 137. This is an infrastructure failure, not a method result.
  - 00814797 in dev4_dx: no model, exit 0. v2 delivers 0.999 on it.
- v2 regression: 00966049 drops from 0.950 (dx) to 0.821 (v2). Not yet diagnosed.
- Caveats:
  - This is the development cohort, used while fixing the code, so the effects are optimistic.
  - The no-model outcomes (for example 00730725, 00966713) vary from run to run, so part of each Δ is run-to-run variance.
  - The held-out fresh2 run is still on hold until the round-2 review.

### Post-dev4 diagnosis (2026-10-21/22): the remaining dev zeros and the 00966049 "regression" are infrastructure and judge artifacts

- **00247424, out of memory in every arm.**
  - The part is a 0.006-thick plate made of sliver triangles. fast_simplification stalls (80,168 → 80,070 faces), and the voxel fallback calls trimesh's `voxelized()`. That subdivides every face down to the pitch: 4^k faces per sliver, more than 1 GB/s of memory growth.
  - The voxel tier could never have succeeded anyway: scikit-image is missing on ORCD, and `VoxelGrid.marching_cubes` ignores the grid transform. Every stalled part therefore already fell back to the original mesh.
  - Fix (516d08a): a stalled mesh keeps the input. The voxel tier (stall above 300k faces only) samples the surface and returns world coordinates.
- **00730725, 00814797, 00966713: no model in some runs.**
  - The log shows every candidate failing with `cq_worker died` from one point on.
  - Each of these parts started while 00247424 was running or just after it, in the same chunk. The node's out-of-memory killer took their persistent CadQuery workers.
  - So the zeros depend on scheduling, not on the arm, and part of the dev3 → dev4 difference is this noise.
  - Fix (516d08a): one retry in a fresh worker, and the root cause above is removed.
- **00966049, dx 0.950 vs v2 0.821: a judge artifact.**
  - Both arms delivered the same program (coordinates differ by about 3e-5).
  - The true IoU against the GT STEP is 0.958: exact manifold boolean of the tessellations 0.9576/0.9576, 400k-point Monte Carlo 0.9557/0.9558.
  - The GT STL is not watertight. The exact path alpha-wrapped it (1.21× the volume) and scored the closed v2 export 0.821. The dx export had a crack, took the winding-number path, and scored 0.950.
  - Fix (f708bb2): an open GT never takes the exact path, and the estimate samples until the union has 10k points. This affects 5 of 60 dev GTs and 26 of 300 fresh2 GTs; only watertightness was checked on fresh2, no outcomes.
  - The judge is shared by exec_verify and the agent tools, so selection and agent feedback on open GTs change too.
- **Next:**
  - Re-score dev3/dev4 with the fixed judge.
  - Run dev5: d0 = e260397 plus the infrastructure patch only (decimation and worker retry, no method change; documented), and dx and v2 at f708bb2.

### Detail recovered, dev3_d0 vs dev4_v2 (2026-10-24, `bench/detail_scores.py`, `results/detail_dev34.json`)
Share of the input surface within 0.01 (0.5% of part size) of the delivered CAD, normalized frame; 0 unless the CAD builds and is OCC-valid.
- All 60 parts, gated: d0 0.851, v2 0.964 (status d0: 52 valid, 3 invalid, 5 no CAD; v2: 59 valid, 1 no CAD = 00247424, the OOM part fixed in 516d08a).
- The 52 parts valid in both: within 0.5% 0.982 vs 0.982, within 1% 0.991 vs 0.990, CAD surface within 0.5% of the input 0.921 vs 0.941, F-score 0.947 vs 0.958, chamfer 0.0032 vs 0.0026; 4 parts better, 4 worse (> 0.005).
- Reading: v2 recovers the same surface detail on parts both deliver; it adds slightly less extra material; the gated gain is from delivering valid CAD. v2 lowest valid part 0.889 (00046097); 49 of 60 at >= 0.95.
- Agent loop now records setup / model / tool seconds (2dc2571); agent-study runtimes in results/runtime_raw.json.

## Run run_20261026_b59bde60 — Round 1 (2026-10-26/27)

### Assessment (Summary)
- Score: 4/10, verdict: not ready (Codex gpt-6-astra xhigh, thread 01a178e8-45a4-7832-8bcd-c78ec9acfe1b). Full response: review-stage/ROUND1_run_20261026_b59bde60.response.md and REVIEWER_MEMORY.md.
- Key criticisms: dev evidence incomplete (dev5, judge-corrected rescoring); gain mostly validity recovery; v2 vs dx unresolved; novelty vs CADFather/CADSmith; agent controls missing (code+section, matched policy, repeats); agent executed score bypassed the judge; runtime confounded by deployment; "detail" conflates validity with fidelity.

### Actions Taken
- 51fcd4d / 340d3cd: precise extents (sweep over the part extent, finer grid on thin directions, ends snapped to cap planes; grid-end extrusion kept as a second candidate). Tests: plates 0.0063–0.4137 thick come out exact; stock drops plates under ~0.02.
- 64ed8a6: early executed fallback (section extrusions through exec-verify when analysis stops before the search); held-out d0 gets bench/d0_infra.patch (infrastructure only), as dev5 d0.
- 9442d7e: agent tools v2 rank executed programs with bench/score.py's robust_iou; model sections draw the executed program.
- 340d3cd: surface agreement = recall/precision/F over tau 0.005/0.01/0.02/0.04, gated; convergence option --n-cad.
- 44dbbe9: section control gets validity-gated fields. 94f9baf: bench/analysis/v2_dev.py (split-stratified paired bootstrap, Holm sign tests, validity decomposition).
- b3c7a81: silhouette trim (exec-verify variant: best valid program ∩ prisms over the target's X/Y/Z silhouettes, grown 0.002); evidence for it: bench/analysis/extra_material.py on 6 dev4_v2 parts, share of extra volume outside silhouettes 3–85%.
- Infrastructure: dev5 OOM chunks rerun at JOBS=3 (same retry policy for every arm); my first dev5 score job passed bare run names and scored nothing (fixed); Gemma needs an H200 at 65k context.

### Results (results/dev345_scores.json, results/dev6_scores.json, results/v2_dev.json; corrected judge; all 60 parts, missing = 0)
| Run | gated IoU(CAD) | benchA | benchE | valid |
|---|---|---|---|---|
| dev5_d0 | 0.8438 | 0.8354 | 0.8521 | 54/60 |
| dev5_dx | 0.9393 | 0.9298 | 0.9488 | 60/60 |
| dev5_v2 | 0.9564 | 0.9557 | 0.9571 | 60/60 |
| dev6_v2 (newer code: + early fallback, agent changes) | 0.9523 | 0.9583 | 0.9464 | 60/60 |
| dev6_v3 (= dev6_v2 + precise extents) | 0.9547 | 0.9583 | 0.9510 | 60/60 |
| dev6_v3 + silhouette trim (post hoc, results/dev6_v3_trim.json) | 0.9584 | | | 60/60 |

Paired (split-stratified bootstrap 95% CI; sign test Holm over the 4 pairs):
- dx − d0 +0.0955 [+0.032, +0.174], 7/0, p_holm 0.063; 82% from parts d0 delivered invalid.
- v2 − d0 +0.1126 [+0.044, +0.193], 12/3, p_holm 0.11; 75% from d0-invalid parts; both-valid +0.032.
- v2 − dx +0.0171 [−0.0004, +0.045], 8/3, p_holm 0.45.
- v3 − v2 +0.0023 [−0.0001, +0.0053], 7/5; thin parts 00140273 0.894→0.942, 00966049 0.957→0.972.
- trim (same delivered programs, with vs without the trimmed variant): +0.0037 [+0.0020, +0.0056], 12 better / 0 worse; chosen on 27/60; post-hoc no-trim reproduces the scored v3 exactly.
- Run-to-run: dev5_v2 0.9564 vs dev6_v2 0.9523 (same flags; dev6 code adds the early fallback, which fired once — dev6_v2 00730725, search left no output — and delivered a valid 0.9491, the score every other run got on that part, so it does not move the mean) — an unseeded-search spread of ~0.004 on the mean.
- Reading: execution verification is the large, robust effect; geometry fixes, precise extents and the trim are small (+0.002 to +0.017) and need the held-out cohort (and repeats) to be established.

### Round 1 actions, continued (2026-10-27/28)
- Surface agreement (bench/detail_scores.py, results/detail_dev56.json). Two measurement defects found and fixed before use: (1) faces buried inside a compound's union were sampled as CAD surface (00492401: same IoU 0.99 in two runs, F 0.95 vs 0.76; 127ec19 samples the outer boundary only); (2) KD distances to surface samples did not converge at tau 0.005 on large-area parts (00883892 recall 0.42/0.75/0.89 at 1M/3M/6M samples; 71fddad uses exact point-to-surface distances, 100k samples per side; two seeds differ by at most 0.0056 over 10 parts x 4 taus x R/P, results/detail_seed_{0,1}.json).
- Results (all 60, gated; R/P/F at tau = 0.5% of part size): d0 0.883/0.870/0.876, dx 0.979/0.967/0.972, v2 0.977/0.967/0.971, dev6_v2 0.965/0.967/0.957, dev6_v3 0.960/0.968/0.956. F v2−d0 +0.095 [+0.029, +0.174]; v3−v2 −0.001 [−0.007, +0.007].
- On the 54 parts valid in all five runs, F at tau 0.25% / 0.5% is 0.951–0.953 / 0.972–0.973 for every run (v2−d0 at 0.25%: −0.002 [−0.014, +0.008]). Surface fidelity does not differ between versions; the gated gains are validity recovery. Precise extents raises IoU on thin parts (00140273, 00966049) without changing surface agreement.
- Section control (results/dev5_v2_section_control.json): best whole-part section extrusion alone 0.845 gated vs v2 0.956; it beats v2 on 0 parts (v2's exec-verify already holds it as a fallback).
- CADFather (2610.09127, commit 2ca0891) installed on ORCD; its programs run in its own env (wrapped DSL), bench/cadfather_adapt.py replays them with our validity check and maps its frame to ours (/100). Smoke on 2 dev parts: valid, and our judge reproduces its own IoU exactly (0.4974, 0.7478); v2 on the same parts 0.873, 0.938. Deviation: 2 x H200 (one assistant replica) instead of its 4 x H100 (ORCD per-user GPU cap), so its wall time is not comparable to the paper's. 60-part dev run queued.
- Agent controls: Gemma-4-31B repeat 1 complete (code/codesec/skills, 20 parts each), repeats 0 and 2 queued (H200); matched scripted policy done; scoring in progress.

## Run run_20261026_b59bde60 — Round 2 (2026-10-28/29)

### Assessment (Summary)
- Score: 5/10, verdict: not ready (full response: review-stage/ROUND2_run_20261026_b59bde60.response.md).
- Confirmed: validity-recovery result credible; agent judge routing, ordinary-failure fallback, d0 infra patch, projected-silhouette trim, section control.
- New defects found by the reviewer: (1) surface metric credits buried faces in recall and skips the boundary filter when an STL roundtrip merges solids (00232213 repair: 139 solids, body_count 1); (2) snapped intervals never reached the search (per-sketch JSON written before snapping); (3) v3/v4 held-out arms not fully frozen. Plus: no unchanged-code repeats; revolve sampling ignored --seed; runtime file covered old configurations only.

### Actions Taken
- 834e868: per-sketch intervals rewritten after snapping; test goes through reload and candidate generation (snapped 0.4137 and grid 0.42 both reach the candidates).
- 88564a5: surface agreement against the fused occupied boundary — bench/union_replay.py replays the program and fuses its solids with OCC (00232213 repair: 139 solids fused in 8 s, watertight, 59% of the compound's tessellated area); winding-number filter only as fallback (it kept 69.5% there, i.e. still some buried faces, and took 31 min). Representation-invariance test (stacked boxes = single box); stacked-box expectation replaced. Full-tree freeze for every requested arm (v2_submit.sh and run_parallel_arms.sh); SEED for repeats; revolve sampling seeded; trim stage timing; v2_dev.py --avg (repeats averaged within part).
- 72fef54: job scripts find apptainer by path; preemptable nodes 17xx/18xx have no /orcd/software (excluded).
- dev7: v2 and corrected v3 (precise extents with snapping reaching the search), SEED 0/1/2, all from one frozen tree (git archive 88564a5), 60 dev parts each. Retry policy as before: OOM-killed chunks rerun at JOBS=2 (chunk 3 on all seeds), preempted chunks resubmitted; every part finished in every run.

### Results (results/dev7s{0,1,2}_scores.json, results/dev7_analysis.json, results/dev7_durations.json, results/dev7s{0,2}_v3_trim.json)
| Run | gated IoU(CAD) | valid |
|---|---|---|
| v2 seed 0 / 1 / 2 | 0.9536 / 0.9531 / 0.9485 | 60/60 each |
| v3 seed 0 / 1 / 2 | 0.9615 / 0.9603 / 0.9595 | 60/60 each |
| v2, mean of 3 seeds per part | 0.9517 | |
| v3, mean of 3 seeds per part | 0.9605 | |
- v3 − v2 per seed: +0.0079 [+0.002, +0.017], +0.0072 [−0.001, +0.019], +0.0111 [+0.003, +0.023]; averaged over seeds within part: +0.0087 [+0.0019, +0.0197], 12 better / 4 worse (sign test, Holm over 6 pairs, 0.23). Same direction on every seed.
- v2 (3-seed mean) − dx: +0.0124 [−0.0023, +0.0379]; − d0: +0.108 [+0.042, +0.188], 73% from d0-invalid parts.
- Trim (post hoc on the same v3 deliveries): seed 0 0.9615 → 0.9662 (+0.0047, chosen 25/60), seed 2 0.9595 → 0.9645 (+0.0050, 26/60); no part lower under the selection judge (by construction). Seed 1 pending.
- Time per part (wall, 48-core node shared by 3 parts at a time (2 on OOM reruns), one run per arm): v2 mean 7.7–9.0 min (median 5.8–6.3), v3 mean 9.2–10.3 min (median 6.1–6.7): precise extents costs ~15% more time. Trim stage: median 17–29 s, mean ~195 s, max 1824 s (silhouette + replay + judge).
- Trim, all three seeds (results/dev7s{0,1,2}_v3_trim.json): +0.0047 / +0.0055 / +0.0050; three-seed mean per part +0.0050 [+0.0026, +0.0079]; 15 parts > +0.005.
- Surface agreement, fused occupied boundary (results/detail_dev56.json; boundary source: fused on every valid part except 1 dx part, winding fallback). All 60 gated F at tau 0.5%: d0 0.836, dx 0.960, v2 0.948, dev6_v2 0.934, dev6_v3 0.931. v2 − d0 +0.112 [+0.031, +0.200]. On the 54 common-valid parts: F 0.929 (d0), 0.959 (dx), 0.946 (v2), 0.947 (dev6_v2), 0.944 (dev6_v3); v2 − d0 +0.017 [−0.032, +0.072], dev6 v3 − v2 −0.003 [−0.040, +0.026]. With the buried faces no longer credited, recall is lower than in the earlier (defective) numbers; no version differs detectably in surface agreement on commonly valid parts. dev7 surface agreement running (job 27578611; per-part cache).
- Held-out protocol proposed: review-stage/HELDOUT_PROTOCOL.md; submission bench/h2_submit.sh; independent re-judge bench/rejudge.py (41cad6b).

## Run run_20261026_b59bde60 — Round 3 (2026-11-01)

### Assessment (Summary)
- Score: 5/10, verdict: not ready for submission; **conditional go for the frozen held-out pipeline study** after bounded amendments (full response: review-stage/ROUND3_run_20261026_b59bde60.response.md). No further method development requested; reviewer recalculated v2 0.95172, v3 0.96045, v3+trim 0.96549 (3-run means), v3−v2 +0.00873 [0.00188, 0.01971], trim +0.00504 [0.00266, 0.00784]; noted ~54% of the dev v3 gain comes from 00247424 alone.
- Required before launch: (1) rejudge/surface on the selected trim artifacts and a fresh2-manifest analysis with completeness checks; (2) runner from the frozen tree, d0 seeding control; (3) explicit secondary family. Clarifications: reserve GPU-study subsets, consistent node exclusions, written post-processing procedure, timing keyed by part with retries.
- Agent attribution (Gemma repeat 1): code+section−code +0.224 [+0.117, +0.339]; skills−code+section +0.0006 [−0.020, +0.022]; skills−policy +0.009 [−0.022, +0.041] — section extrusion explains nearly all the tools gain so far.

### Actions Taken (f7455d3)
- trim_posthoc records the selected program/STL; bench/rejudge.py judges the delivered artifact (score runs: replayed program; trim: selected variant), independent seed and 4x samples, never reselects, refuses incomplete runs; bench/detail_scores.py --trim scores the selected variant with its own fused boundary.
- bench/analysis/v2_dev.py: --manifest (fresh2), --trim, --section; refuses runs lacking a record for any manifest part.
- bench/arms_job.sh runs ${RUNNER_SRC}/bench/run_parallel_arms.sh (held-out: the frozen bench/runs/h2_src); bench/d0_seed.patch (revolve sampling seeded) applied to d0 with the infra patch.
- HELDOUT_PROTOCOL.md amended: primary dx−d0 alone; secondary family exactly v2−dx, v3−v2, trim−v3, trim−section-only (Holm over these four sign tests); d0/dx single-run references; per-run and every-repeat validity; node exclusion list = h2_submit.sh EXCL; post-processing order bench/h2_post.sh; timing via bench/analysis/timing_export.py (per run/part, attempts, concurrency, trim seconds).
- Reserved GPU-study subset: bench/cadbench/fresh2_subset.json (20+20, random.Random(20261101), manifest only).
- Dev dry run of the secondary family: v2x3−dx +0.0124 [−0.0023, +0.0379]; v3x3−v2x3 +0.0087 [+0.0019, +0.0197]; trim−v3 +0.0050 [+0.0027, +0.0078]; trim−section +0.1207 [+0.0798, +0.1653].
- Smoke test on dev outputs (scratch/smoke_rejudge.json): 00046097 (trim selected) re-judged on exec_original_trim.stl, 0.93758 → 0.93806 (MC, 40,391 union samples); 00090768 (original retained) re-judged on exec_original.stl, exact, 0.99376 unchanged; surface for 00046097 used the trimmed program's fused boundary.

### Launch
- 2026-11-01 17:14 EST: `COMMIT=f7455d3 bash bench/h2_submit.sh` on ORCD. Frozen: h2s0_d0_code (git archive e260397 + d0_infra.patch + d0_seed.patch), h2s0_dx_code, h2s{0,1,2}_{v2,v3}_code, h2_src (git archive f7455d3). Jobs 27589626 (h2s0: d0 dx v2 v3), 27589627 (h2s1: v2 v3), 27589629 (h2s2: v2 v3), 12 chunks each. No fresh2 outcome had been produced or inspected before this point.
- dev7 surface agreement (results/detail_dev7.json, fused boundary; winding fallback on 1/1/2 v3 parts across seeds, flagged): F at tau 0.5%, 3-seed mean per part: v2 0.930, v3 0.956, v3−v2 +0.026 [−0.006, +0.062]; recall 0.926 → 0.954, precision 0.969 → 0.969. Diagnostic only; interval includes 0.
- Smoke test complete: 00090768's retained original did not fuse → surface via the flagged winding fallback (F 0.986); 00046097 trimmed variant fused (F 0.842).
- Held-out generation (2026-11-02): most chunks report OUT_OF_MEMORY (oom_kill events of worker processes inside parts) or TIMEOUT (chunk 6, part 00979463, in h2s0/h2s1/h2s2), but parts completed: h2s0 d0 296, dx/v2/v3 299; h2s1 v2/v3 299; h2s2 v2 298, v3 300. Per protocol, the chunks holding the 11 missing part-runs were rerun once at JOBS=2 (27671703–05).

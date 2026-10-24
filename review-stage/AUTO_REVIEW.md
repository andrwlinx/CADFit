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

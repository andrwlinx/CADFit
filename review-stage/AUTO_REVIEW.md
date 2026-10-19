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

# Research review request — CADFit++ (2026-10-14)

Repo: /Users/Andrewlin/CADFit (branch `cadfitpp-candidate-ranking`; HEAD c291cef plus
uncommitted agent changes). Base system: CADFit (MIT DeCoDE lab), mesh → CadQuery program
reconstruction: slice the mesh, extract planar sketches, fit primitives, build candidate
extrude/revolve/cut solids, greedy-select a union/cut composition by IoU, refine.

The primary result log is `bench/RESULTS_2026-10-09.md` (read all of it). Earlier phases:
`bench/REPORT.md`, `REPORT2.md`, `REPORT3.md`. Scoring: `bench/score.py` (independent judge;
exact robust booleans for CADBench, "soup judge" for raw ABC meshes that are open triangle
soups). The pipeline's own printed IoU is never used.

## Candidate contributions

1. **Engineering of the search (CADBench).** Rules flags + exact-union manifold scoring +
   seeded beam search (`--beam 4`). CADBench test (100 benchA-hard parts, frozen):
   stock 0.8445 → 0.9032 (`bench/runs/p3test_scores.json`, `p3test2_scores.json`).
   Dev results with bootstrap CIs in REPORT3.md.
2. **Winding-number repair of open meshes (`gwn_repair.py`, `--gwn-repair`).** Raw ABC meshes
   from the lab are often open soups. abc40 (development) and abc60 (held out, seed 1):
   beam 0.663 → beam+repair 0.725 after the §6/§6b bug fixes
   (`bench/runs/abc60c_ws/abc60cr_pscores.json`). Note: abc60 was used to find bugs
   that were then fixed and re-run, so it is not cleanly held out any more.
3. **LLM agent with CADFit stages as tools (`agent/`).** Tools: describe_target,
   list/show/add candidates, add_code (sandboxed CadQuery), remove_step, evaluate
   (missing/extra regions), section, export. Modes: refine (start from pipeline result;
   best model is kept so refine cannot go below the pipeline) and scratch.
   Eval = the 10 weakest CADBench test parts under beam (pipeline mean 0.6264). Budget
   40 tool calls / 20 min. Local vLLM.
   - Qwen2.5-Coder-14B: refine 0.6305, scratch 0.3172
   - Qwen2.5-32B: refine 0.6273, scratch 0.5443
   - Qwen3.8-27B-INT4 (thinking): refine 0.7232 / 0.6947 / 0.6816 over 3 runs
     (0.700 ± 0.021), scratch 0.5685 (1 run). Two parts win every run (00182325 0.52→0.92,
     00875997 0.77→0.93). Scores: `bench/runs/agentq38b/scores.json`, `agentq38r2/`,
     `agentq38r3/` (some may live only on the workstation; the RESULTS doc tables are the
     copies).
   Code: `agent/agent_loop.py`, `agent/cad_tools.py`, `agent/run_agent_bench.py`.

## Known weaknesses (author's own list)

- Agent eval is n=10, chosen as the pipeline's *weakest* parts (selection on the baseline →
  regression to the mean is possible in principle, though refine starts from the same model).
- Refine keeps the best model by the agent's own evaluate() score, then the judge scores it;
  the agent's evaluate and the judge differ.
- Compute is not matched: the agent gets 20 extra minutes per part; no "pipeline + 20 more
  min of search" or best-of-N pipeline control.
- Sampling differs between Qwen2.5 runs (T=0.2) and Qwen3.8 (T=1.0).
- No external baselines (e.g. other mesh/point-cloud → CAD methods, or a frontier API model).
- abc60 reuse after bug fixes (see 2).

## Questions

1. What can honestly be claimed today from each of the three lines of work?
2. Which is the strongest paper story, and is it enough for a top venue (or a workshop)?
3. What is the minimum experiment package to make the main claim defensible? Compute:
   one workstation with 88 CPU threads, 1x RTX 4090 24 GB (a second may be free), ~16 GB
   free disk; Mac for dev. Each pipeline part ~15–20 min at ~15 cores; agent run 20 min/part.
4. Any bugs or measurement errors you can find in the scoring or agent loop that would
   invalidate the numbers.

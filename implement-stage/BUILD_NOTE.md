# Build Note — open-model CAD agent with CADFit skills

| Rung | Feature | Acceptance check (ONE command) | Tier | Status |
|------|---------|-------------------------------|------|--------|
| F0 | spine: `--toolset skills` + `scripted:` model backend → result.json, stub skills | `.venv/bin/python agent/agent_loop.py --toolset skills --model scripted:tests/agent_scripts/spine.json --gt tests/meshes/plate_hole.stl --out /tmp/agentsk_spine && test -f /tmp/agentsk_spine/result.json` | MUST | ✅ |
| F1 | real detect_directions + extract_sketch | `.venv/bin/python -m pytest -q tests/test_agent_skills.py -k "directions or extract"` | MUST | ✅ |
| F2 | real fit_extrude (extents → evaluated candidates) | `.venv/bin/python -m pytest -q tests/test_agent_skills.py -k extrude` | MUST | ✅ |
| F3 | real fit_revolve + section_extrude; `code` toolset | `.venv/bin/python -m pytest -q tests/test_agent_skills.py` | MUST | ✅ |
| F4 | skills on real fresh parts via a scripted no-LLM policy | `.venv/bin/python agent/scripted_skills_policy.py --smoke && test -f /tmp/agentsk_policy/summary.json` | MUST | ✅ |
| F5 | ORCD harness: vLLM env, per-model serve config, Slurm episode runner; smoke with one model | `ssh orcd test -f /orcd/pool/007/a_lin/cadfit/bench/runs/agentsk_smoke/gptoss-20b/summary.json` | MUST | ✅ |
| F6 | study: models × {skills, code} × 20 parts, scored | `ssh orcd 'cd /orcd/pool/007/a_lin/cadfit && test -f bench/runs/agentsk_scores.json'` | MUST | ⬜ |
| F7 | report: tables, tool-use stats, figure | `.venv/bin/python bench/agent_skills_report.py && test -f bench/AGENT_SKILLS_RESULTS.md` | SHOULD | ⬜ |

## Run record
<!-- one line per rung attempt: command, exit code, artifact, fix attempts used -->
- F0: spine check exit 0; /tmp/agentsk_spine/result.json (best IoU 0.9182, box without hole); 0 fixes. pool prompt/tools verified byte-identical to 5f90fac.
- F1: 6 passed, exit 0; 1 fix (rotated-bracket test assumed detect_directions.py returns cap normals — it excludes them by design; skill now adds flat-face normals, A-014). F0 re-run exit 0.
- F2: 4 passed (plate_hole and bracket recovered at IoU>0.98 from one sketch; exported agent_model.py rebuilds the same volume), exit 0; 0 fixes. F0, F1 re-run exit 0.
- F3: 13 passed, exit 0; 1 fix: shaft revolve IoU 0.408 → 0.994 after densifying the split profile (pipeline bug, A-016); revolve axis now reported in world coords. No PLACEHOLDER left in agent/skills.py. F0 exit 0.
- F4: smoke exit 0 on the first 3 study parts (00046097 0.781, 00095369 0.899, 00140273 0.894 agent-visible IoU; 34-247 s, 16-19 calls, within 40 calls / 30 min); slowest calls fit_revolve ~50 s, off-axis extract_sketch ~22 s. 0 fixes. F0-F3 green.
- F5: 4 smoke attempts (gpt-oss-20b, 1 part, both toolsets). Fixes: (1) vLLM venv on system python3.12 lacked Python.h → uv-managed Python; (2) FlashInfer JIT sampler needs nvcc → cuda module + VLLM_USE_FLASHINFER_SAMPLER=0; (3) bwrap cannot rebind / on GPU nodes → ns_sandbox fallback (A-018); (4) cold cadquery import 88 s → warm-up in job; (5) gpt-oss tool-name residue → clean_tool_name (A-021). Attempt 4: summary.json exists, 2/2 episodes, skills IoU 0.727 in 8 calls, code-toolset add_code ran in the sandbox. Acceptance path corrected to <tag>/<model>/summary.json. Local tests 13/13 also pass on ORCD CPU nodes.

## Deferred
- Loft/sweep (`analyze_sweep_loft.py`) as a skill — exists only behind CADFIT_SWEEP_LOFT; low hit rate on CADBench.
- Models needing more than one GPU (GLM-5.3 753B, GLM-5.3-Flash 321B, DeepSeek-V4.1-Flash 763B).
- Repeats per cell beyond one (variance estimate) — only if F6 leaves GPU time.

## Blockers

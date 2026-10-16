# SPEC — open-model CAD agent with CADFit stages as skills

**Request (verbatim):** "test open source models to do an agentic loop for cad generation while giving it skills
like the different steps from CADFit (ability to extract sketches, measure iou against input mesh etc). use a very
high effort, plan this out, and execute autonomously"

**Mode:** EFFORT=max (rung budget 8, assurance=submission), ASK=never.

**Target.** (1) `agent/skills.py`: CADFit's analysis stages exposed as on-demand agent tools — detect extrusion
directions, extract a sketch at any plane (slice → loop split → line/arc fit), fit extrusion extents, fit revolve
axes, whole-part section extrusion — on top of the existing workspace tools (describe/section/evaluate/add_code).
Selected with `agent_loop.py --toolset skills`, starting from an empty model (generation, not refinement).
(2) A study on ORCD: several open-weight models × {skills, code-only} toolsets on fresh-cohort parts, scored with the
corrected judge and CAD replay, against the deterministic pipeline arms.

**Inputs.** Target STL (fresh cohort `bench/cadbench/fresh`), an OpenAI-compatible endpoint (vLLM on ORCD GPUs).

**Outputs.** Per episode `bench/runs/agentsk_<model>_<toolset>/<part>/{result.json,agent_model.stl,agent_model.py,
transcript.jsonl}`; scores `bench/runs/agentsk_scores.json`; report `bench/AGENT_SKILLS_RESULTS.md`.

**Success command (spine).** `.venv/bin/python agent/agent_loop.py --toolset skills --model scripted:tests/agent_scripts/spine.json --gt tests/meshes/plate_hole.stl --out /tmp/agentsk_spine && test -f /tmp/agentsk_spine/result.json`

**Base commit.** `5f90fac` (Phase C baseline, committed just before this run).

**Scope cuts.** No fine-tuning; no models needing >1 H200 (GLM-5.3, DeepSeek-V4.x) — deferred; no change to the
existing `pool`/refine toolset's behaviour; loft/sweep stage not exposed as a skill (deferred).

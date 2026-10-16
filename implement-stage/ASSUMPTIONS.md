# Assumption Ledger — open-model CAD agent with CADFit skills
<!-- ASK mode: never -->

| ID | Under-determined by the request | Chosen | Class | Source |
|----|--------------------------------|--------|-------|--------|
| A-001 | "agentic loop for CAD **generation**" — from scratch or refining the pipeline's output? | From scratch: empty model, no pipeline init, no precomputed candidate pool. Candidates exist only if the agent makes them with skills. | semantic | default |
| A-002 | which "steps from CADFit" become skills | detect_directions, extract_sketch (slice → split_loops grouping → fit_primitives line/arc fit), fit_extrude (analyze_loop_translation CD sweep → extents), fit_revolve (analyze_revolve_axis), section_extrude (section_extrude.py, agent picks axis/plane); plus existing describe_target, section, evaluate (IoU vs input mesh), add_code, add_candidate, remove_step, list_steps, finish. **Not** exposed: greedy search / the whole pipeline as one call. | semantic | default |
| A-003 | what the models are compared against | Per model: toolset `skills` vs toolset `code` (identical minus the CADFit stage skills and candidates). External references: pipeline arms `fresh_beamsec` and the best-of section control from `fresh_scores.json` / `fresh_section_control.json` (not rerun). | semantic | default |
| A-004 | which "open source models" | Open-weight panel, each fits one H100/H200: Qwen/Qwen3.8-27B-FP8, Qwen/Qwen3.6-35B-A3B-FP8, google/gemma-4-31B-it, openai/gpt-oss-120b, openai/gpt-oss-20b, mistralai/Devstral-Small-2-24B-Instruct-2512. Multi-GPU giants (GLM-5.3, DeepSeek-V4.1) deferred. | semantic | default |
| A-005 | which parts | 20 parts drawn with `random.Random(1).sample` from the 60-part fresh cohort (sorted names), fixed before any agent outcome. Not gated on pipeline IoU (generation, not repair). | semantic | default |
| A-006 | episode budget | 40 tool calls and 30 min wall clock per episode, identical for both toolsets; skill compute time counts against the clock. | semantic | default |
| A-007 | what the episode's answer is | Best model seen during the episode by the agent-visible exact manifold IoU against the target (existing loop behaviour) — i.e. selection uses ground-truth feedback, same for every condition. | semantic | default |
| A-008 | metric | Final judge `bench/score.py` (robust IoU, normalized frame) on `agent_model.stl`, plus CAD replay of `agent_model.py` (`iou_cad`, `cad_valid`). Headline = mean IoU(CAD) over all 20 parts; a failed/missing episode scores 0. | semantic | default |
| A-009 | decoding settings | Each model's model-card recommended sampling; thinking/reasoning on where supported; one episode per (model, toolset, part). | semantic | default |
| A-010 | how the feature is selected | `agent_loop.py --toolset {pool,skills,code}`, default `pool` (existing behaviour unchanged); `run_agent_bench.py --toolset --jobs` for concurrent episodes. | interface | default |
| A-011 | where skill code runs | CADFit skills run in-process (trusted repo code); agent-written CadQuery stays sandboxed (bwrap/sandbox-exec) as before. | interface | default |
| A-012 | determinism of skills | Surface sampling inside fit_extrude/fit_revolve seeded (seed 0); results cached per sketch so a repeated call is free and identical. | interface | default |
| A-013 | extract_sketch loop filtering | Keep rectangular loops (the pipeline drops them as a batch-mode heuristic; an agent asking for a slice wants what is there). | interface | default |
| A-014 | detect_directions skill: the pipeline stage omits flat-face normals (another stage covers them) | Skill returns detect_directions.py's off-axis directions **plus** describe_target's flat-face normals and plane offsets | interface | default |
| A-015 | stage settings inside skills | Same as the fresh-cohort pipeline arms: CADFIT_FAST_CD=1, CADFIT_TRANSLATION_MAXPTS=400, translation range [-2, 2] step 0.01, 100k surface samples (seed 0); extents → candidates by greedy_search.create_extrusion_from_translation (≤5 largest intervals) | interface | default |
| A-016 | revolve profile split is buggy in the pipeline (on-axis edge has 2 points; line fit drops the axis corner: stepped shaft revolved to 40% volume) | Fixed behind `greedy_search.DENSIFY_REVOLVE_SPLIT` (default False, so pipeline arms stay reproducible); `agent/skills.py` sets it True. The agent's fit_revolve is therefore *better* than the revolve stage inside the frozen pipeline arms. | semantic | default |
| A-018 | sandbox for agent code on ORCD GPU nodes, where bwrap cannot rebind / inside Apptainer | `agent/ns_sandbox.py` via `unshare -rnm`: all mounts remounted read-only, tmpfs on /tmp,/var/tmp,/dev/shm, workdir bound rw, fresh netns. Used only when a bwrap probe fails. Verified on a GPU node: workdir write OK; pool/home writes, deleting a pool file, and network all blocked. | interface | default |
| A-019 | serving stack | vLLM 0.31.0 (uv-managed Python 3.12.15), `module load cuda/13.0.1`, `VLLM_USE_FLASHINFER_SAMPLER=0` (FlashInfer JIT sampler needs nvcc at warm-up); max-model-len 65536, gpu-memory-utilization 0.90 | interface | default |
| A-020 | per-turn generation and context limits | max_tokens 16384 per model turn; `--keep-tool-results 6` (older tool results truncated to 300 chars in what is sent); identical for every model | semantic | default |
| A-017 | what the no-LLM skills control does | `agent/scripted_skills_policy.py`: mid-plane sketches along axes, flat-face normals and detected directions; fit_extrude all, fit_revolve axis sketches; section_extrude x/y/z; greedy add/cut by GT IoU gain ≥ 0.001; same 40-call / 30-min budget | semantic | default |

## Notes

- **A-001** — The request says *generation*. The earlier agent study (refine mode, precomputed pool) already
  measured "agent improves the pipeline's answer" and found ≈ no gain; the new question is whether an open model
  can *build* a model by driving CADFit's stages itself. Refine/pool mode stays available (`--toolset pool`).
- **A-002** — Exposing the whole pipeline as one skill would make the best policy "call it once", which measures
  the pipeline, not the agent. Its result is still reported as an external baseline (A-003). Override: add a
  `run_pipeline` tool in `agent/skills.py`.
- **A-006** — Wall clock is charged for skill compute, so the `skills` toolset pays for its analysis. A
  calls-only budget would favour skills; the earlier study used 40 calls / 20 min, raised to 30 min here because
  fit_extrude/fit_revolve take seconds to a minute each. One flag each in the Slurm script.
- **A-007** — Inherited from the existing loop. It makes the episode's answer a GT-selected best-of-trajectory,
  which is optimistic; every condition (and the best-of section control) shares it, and the report must say so.
- **A-008** — IoU(CAD) is the headline because the request is CAD *generation*: a mesh that matches but whose
  program does not rebuild is not a CAD model (cf. 00090768: mesh 0.999, CAD 0.002).
- **A-016** — Found while building fit_revolve (shaft test: 0.408 → 0.994). The pipeline arms in
  `fresh_scores.json` ran with the bug, so "agent with skills vs pipeline" is not a same-stage comparison for
  revolves; the report must say so. Fixing the pipeline itself (flag default True) and rerunning its arms is the
  clean resolution — out of scope for this run, listed under Next.

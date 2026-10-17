# NARRATIVE_REPORT — CADFit++: measurement, geometric proposals, and CAD skills for open-model agents

All numbers below are recomputed by `bench/paper_stats.py` into `results/fresh_arms.json`,
`results/agent_skills.json`, `results/refine_study.json`. CIs are paired percentile bootstrap over
parts (10,000 resamples, seed 0). "IoU" = volumetric IoU of the output mesh vs. the ground truth
(normalized frame, largest extent → [-1,1]); "IoU(CAD)" = the same judge on the solid obtained by
*executing the final CadQuery program* in a fresh sandboxed process (0 if it does not build).

## 1. Problem and setting

Mesh-to-CAD: given a watertight triangle mesh, output an executable, editable CAD program
(CadQuery: sketch → extrude/revolve, union/cut) whose solid matches the mesh. CADFit
(Nehme, Whalen, Ahmed; arXiv 2605.01171) does this by IoU-driven optimization: it slices the
mesh into planar sketches, fits line/arc primitives, proposes extrusion/revolve candidates
(translation CD sweep, revolve-axis analysis), and greedily composes them with booleans,
followed by backward pruning and residual refinement.

Benchmark: CADBench (`DeCoDELab/CADBench`, Hugging Face; same lab), splits benchA and benchE,
"hard" tier (face-count tier; benchA-hard = ABC shapes with 138–12,292 B-rep faces). benchA-hard
geometry is 77.6% planar area, 18.5% cylindrical; 83.2% of planar area has an axis-aligned normal
(`bench/gt_surface_stats.py`, 158 GT STEP files). Gotcha: split names and file prefixes are swapped
(benchA = `bench1B-*`, benchE = `bench1A-*`).

**Fresh cohort (the evaluation set):** 30 benchA-hard + 30 benchE-hard, seeded draw taken after all
earlier sets (test/dev/smoke) and excluding every file_id ever downloaded — never inspected
during development. All headline numbers are on this cohort. One run per (method, part).

## 2. Contribution 1 — Measurement: what the CADFit objective and judge get wrong

Found while developing (dev/smoke sets) and confirmed by an external Codex review:

1. **Biased search objective.** Stock greedy concatenates candidate STLs; overlapping compounds fail
   the single-body check, so the whole model is alpha-wrapped before IoU is taken. Alpha-wrap fills
   concave detail (smoke part 00053793: search believed 0.954, strict judge 0.982), the bias varies
   per candidate, so it changes which candidates are accepted. Fix: `--exact-union` (manifold3d exact
   union of cached per-candidate solids).
2. **Judge fills cavities.** Body-wise union of split bodies included negative-volume cavity shells
   (00344388: 0.9758 → 0.9862; 00014841: 0.9102 → 0.9475 after the fix).
3. **Mesh fidelity ≠ executable CAD.** With exact-union scoring the reported mesh comes from manifold
   booleans; the combined CadQuery program was never executed. We add CAD replay: run the final program
   in a fresh sandboxed process, check OCC validity of the shape and every solid, tessellate, judge.
4. **Self-intersecting lofts** pass watertight/winding/`isValid()` checks but cancel volume (one made
   greedy believe 0.998 on a part whose true score was 0.776); rejected by an alpha-wrap volume ratio test.
5. **Silent failures:** trimesh API change drops fallback slices (7 times on 4 smoke parts); pipeline
   reports success when greedy crashes; alpha-wrap segfaults kill the pipeline (now isolated).

**Headline measurement result (fresh 60, `results/fresh_arms.json`):** the mesh–CAD gap grows with
search strength. Mean IoU vs IoU(CAD), and parts whose program does not build or is OCC-invalid:

| arm | IoU | IoU(CAD) | CAD unbuilt or invalid (of 60) |
|---|---|---|---|
| A base (corrected stock) | 0.820 | 0.822 | 2 |
| B + rules | 0.877 | 0.830 | 6 |
| C + beam | 0.880 | 0.799 | 9 |
| D + beam + section proposals | 0.938 | 0.889 | 5 |

Paired mesh-IoU gains are significant at every step (B−A +0.056 [+0.027,+0.098]; C−B +0.003
[+0.0004,+0.007]; D−C +0.058 [+0.026,+0.101]; D−A +0.117 [+0.070,+0.175]). On IoU(CAD) only D−C is
significant (+0.089 [+0.008,+0.174]); B−A (+0.009 [−0.058,+0.070]) and C−B (−0.031 [−0.095,+0.029])
are not, and D−A is +0.067 [−0.012,+0.144]. Message: a large part of apparent search gains on mesh
IoU does not survive executing the program; evaluation of mesh-to-CAD must execute the program.

## 3. Contribution 2 — CADFit++ search: rules, beam, and whole-part section proposals

Flag-gated additions (stock reproducible):
- **Rules (arm B):** `--persistent-cq` (90% of each CadQuery call was interpreter startup; byte-identical
  STLs), `--exact-union`, `--cut-phase` (subtract candidate solids while IoU improves — near-zero-IoU
  candidates are hole tools), `--event-slices` (slice between consecutive heights of axis-normal planar
  faces so thin layers get their own section), `--detect-directions` (Gauss-map extrusion directions:
  cluster face normals, cross products of cluster pairs, scored by wall area; oblique prism recovered
  within 0.012°), `--translation-max-points 400`.
- **Beam (arm C):** beam search (width 4) over compositions on exact IoU, motivated by path dependence
  (a worse greedy start can end better after refinement).
- **Section proposals (arm D):** for each axis, the mid-bounding-box cross-section of the target,
  simplified (0.002) and extruded through the full extent, added as candidates. Origin: an external
  reviewer found this trivial control beat an LLM agent (control 0.748 vs agent 0.700 mean of 3 on 10
  hard test parts; designed post hoc). We froze the recipe on dev and folded it into the pipeline.

Results (fresh 60): D is the best arm on both metrics (IoU 0.938, IoU(CAD) 0.889, CD 0.0104).
benchE-hard benefits most (IoU(CAD) 0.777 → 0.918, A → D). The standalone "best of C and sections"
control (pick the better of arm C's model and the best section extrusion per part) gives IoU 0.953 /
IoU(CAD) 0.902; D − best-of on IoU(CAD) = −0.014 [−0.080, +0.053] (not distinguishable). Section
extrusions alone (best axis per part, no search) reach IoU 0.842, above the corrected base arm (0.820).
Message: on this benchmark (mostly axis-aligned 2.5D), whole-part section proposals are a strong prior
the stock proposal generator lacked; beam adds little on its own.

## 4. Contribution 3 — CADFit stages as tools for open-weight LLM agents

Agentic loop (OpenAI-compatible tool calling, vLLM 0.31 on H200s): the agent sees the target mesh
(stats, renders via tools), can call `evaluate` (exact IoU vs target, precision, coverage) and add/cut
candidates or CadQuery code; the episode answer is the best model seen by that IoU (ground-truth
feedback, same for every condition). Budget: 40 tool calls, 30 min. From scratch: no pipeline output.

Two toolsets per model, same budget:
- **code:** write CadQuery, evaluate, read sections (exact profiles).
- **skills:** + CADFit stages wrapped as tools: `detect_directions`, `extract_sketch(normal, offset)`
  (slice → loop nesting → line/arc fit), `fit_extrude(sketch)` (translation CD sweep → extents),
  `fit_revolve(sketch)` (revolve-axis analysis), `section_extrude(axis)`.
Implementation details that mattered: even-odd loop nesting (pipeline grouping called an island in a
hole a second hole), keeping profiles ≥1e-6 area (pipeline's 1e-3 dropped all 67 profiles of one part),
a revolve-profile split bug fixed for the skill (stepped shaft 0.408 → 0.994; frozen pipeline arms do not
have this fix), tool results capped at 8,000 chars as valid JSON, agent code sandboxed (bwrap or a
user-namespace sandbox with read-only remounts, verified, then capability drop).

Six open-weight models, each on one GPU: Gemma-4-31B-it, Qwen3.6-35B-A3B (FP8), gpt-oss-120b,
Devstral-Small-2-24B, gpt-oss-20b, Qwen3.8-27B (FP8). Model-card sampling, thinking on, 16k tokens per turn.
20 parts drawn (`random.Random(1)`) from the fresh cohort before any run (12 benchA, 8 benchE).
Control: **no-LLM skills policy** — a script that calls section_extrude on x/y/z, mid-plane sketches,
fits the 3 largest profiles per plane, then greedy union/cut assembly; it additionally scores ~69
candidate unions/cuts per part against the GT without spending tool calls (a ceiling-style control
with more oracle access than an agent). References: pipeline arms C, D, best-of on the same 20 parts.

Results (mean IoU(CAD), 20 parts, failures = 0; `results/agent_skills.json`):

| model | skills | code | skills − code [Bonferroni 99.17% CI] | wins–losses |
|---|---|---|---|---|
| Gemma-4-31B | 0.892 | 0.593 | +0.299 [+0.135, +0.481] | 17–3 |
| Qwen3.6-35B-A3B | 0.854 | 0.465 | +0.389 [+0.208, +0.565] | 17–3 |
| gpt-oss-120b | 0.812 | 0.557 | +0.256 [+0.112, +0.419] | 18–2 |
| Devstral-Small-2-24B | 0.776 | 0.305 | +0.471 [+0.316, +0.612] | 19–1 |
| gpt-oss-20b | 0.732 | 0.422 | +0.311 [+0.105, +0.520] | 15–5 |
| Qwen3.8-27B | 0.730 | 0.307 | +0.423 [+0.179, +0.664] | 15–3 |
| no-LLM skills policy | 0.810 | | | |
| pipeline D (beam+sections) | 0.904 | | | |
| pipeline C (beam) | 0.860 | | | |
| best-of C and sections | 0.896 | | | |

- Skills > code for all six models, every Bonferroni CI excludes 0.
- Gemma-4 + skills vs pipeline D: −0.012, Bonferroni CI [−0.050, +0.043]; 6–10 parts. Not shown
  different; within ~0.05. (Not an equivalence test.)
- LLM vs no-LLM policy: Gemma +0.083 (95% CI [+0.013, +0.188]; Bonferroni [0.000, +0.233]; sign test
  10–4, p = 0.18) — not significant after correction. Others: −0.080 … +0.044, none significant.
  So the skills, not the LLM's planning, explain most of the gain at this sample size.
- Failure modes: Qwen3.8 at 16k/turn ends 16/20 code episodes with no tool call (thinking exhausts the
  turn). Post-hoc 32k sensitivity (decided after seeing outcomes; not part of the study): skills
  0.730 → 0.783, code 0.307 → 0.541. gpt-oss-20b: 3 episodes lost to leaked harmony tokens (HTTP 500).
- Tool use (skills): extract_sketch 1.8–4.9 and fit_extrude 1.6–6.8 calls/episode; fit_revolve ≤0.3 —
  the parts barely exercise revolves.

Earlier study (refine, not from scratch): Qwen3.8-27B-INT4 refining arm C's output on the 19 fresh parts
with judge IoU < 0.90 (gate fixed before running), 2 repeats, mesh IoU: pipeline 0.751; agent 0.797 and
0.807 (W/L 2/3 and 4/3 vs pipeline at ±0.01); no-op re-export 0.749; equal-time scripted search 0.756
(W/L 8/2). Mean gain driven by few parts; not consistent per part. (`results/refine_study.json`)

## 5. Related work pointers

CADFit (2605.01171); CADBench; ABC dataset (Koch et al. 2019); DeepCAD (Wu et al. 2021); Fusion 360
Gallery (Willis et al. 2021); Point2Cyl (Uy et al. 2022); CAD-Recode / CAD-as-code LLM methods; CADFather
(arXiv 2610.09127, LLM CAD agent, concurrent); generalized winding numbers (Jacobson et al. 2013);
manifold3d; CadQuery; OpenCascade; vLLM; tool-using LLM agents (ReAct, Toolformer, SWE-agent).

## 6. Limitations (real)

- One episode/run per cell; CIs reflect part sampling only.
- 20 parts for the agent study; 60 for the pipeline; hard tier of two CADBench splits only; axis-aligned
  2.5D dominates (revolve skill barely used).
- Agent answers and the policy are selected with ground-truth IoU (as is the pipeline's own objective);
  absolute numbers assume the target mesh is available — true for mesh-to-CAD, but the agent never has to
  decide when it is done without that feedback.
- The no-LLM policy has extra free GT evaluations (~69/part); agents pay per evaluate call.
- The agent fit_revolve has a bug fix the frozen pipeline arms lack.
- Section proposals originated from a post-hoc control designed after seeing agent results on test parts;
  the recipe was frozen on dev and evaluated on the fresh cohort.

## 7. Figures available
- `bench/figures/agent_skills_iou_cad.png` — bar chart of IoU(CAD) per condition (20 parts).
- Data for: arm ladder (mesh vs CAD IoU, 60 parts), skills vs code paired scatter, per-split bars.
- Method diagram needed: pipeline stages → skills exposed as tools → agent loop.

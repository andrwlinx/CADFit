# Narrative report — Execute the Program (rebuilt 2026-11-07)

Supersedes NARRATIVE_REPORT.pre_2026-11-07.md. Every number below cites its file. "Pending"
marks preregistered outputs not yet computed (they are running on ORCD); the paper must use
visible placeholders for them.

## One-paragraph story
The output of mesh-to-CAD reconstruction is a program, so it should be judged by executing it.
We build an execution-based evaluation (sandboxed replay of the delivered CadQuery program, OCC
validity of the shape and every solid, IoU of the executed solid against the target, invalid = 0)
and use it in three frozen, prospectively specified studies on CADBench hard-tier parts. (1) A
reconstruction optimizer (CADFit) delivers a program that does not build or is OCC-invalid on
41/300 held-out parts; making delivery execution-verified (pick the best program that actually
builds valid CAD, repair if not) raises validity-gated IoU by +0.104 (preregistered primary
contrast), and later geometry fixes, precise extents and a silhouette trim add smaller,
significant increments. (2) Under the same judge, frontier closed models (Claude Opus/Sonnet
5.5) acting through a CAD harness with plain code reach 0.975 (Opus) on 40 reserved held-out
parts, above the optimizer's v3 (0.951); the optimizer's own stages exposed as agent tools did
not help and caused deadline failures. (3) Profiling showed the tool cost was implementation
overhead, not geometry; exact rewrites plus a per-check time cap ("tools v3"), developed only on
development parts and evaluated on a new source-disjoint cohort, halve Opus's time with CADFit
tools, remove no-output episodes, and make CADFit tools slightly but significantly better than
plain code; the preregistered primary (tools v3 vs v2 for Opus+CADFit tools) is not significant.

## Evaluation protocol (method)
- Judge: bench/score.py robust_iou — exact manifold booleans when both meshes are closed and
  consistent, else seeded Monte-Carlo with generalized winding number (Jacobson 2013); GT
  normalized to [-1,1]. Executed program: bench/cad_replay.py in a sandbox (bwrap / sandbox-exec),
  OCC isValid on the shape and on every solid; 900 s replay limit. Metric: validity-gated IoU
  (iou_cad_gated): IoU of the executed solid if it builds valid, else 0; missing output = 0.
- Statistics: paired over parts; split-stratified bootstrap (benchA/benchE) 95% intervals;
  exact sign tests; Holm within declared families. Repeats averaged within part.
- Cohorts (bench/fetch_cadbench.py, seeded, source-model disjoint): dev (60), fresh (60) and
  others used for development; fresh2 (300: 150 benchA-hard + 150 benchE-hard) held-out for the
  pipeline; 40 of fresh2 reserved for agent studies (bench/cadbench/fresh2_subset.json, drawn
  before any fresh2 outcome); fresh3 (40, drawn after the tools-v3 code and protocol were frozen,
  excluding every source model in any earlier set) for the tools study.

## Study 1 — held-out pipeline (review-stage/HELDOUT_PROTOCOL.md)
Arms (frozen trees): d0 = released pipeline + infrastructure/seed patches; dx = d0 +
execution-verified delivery (exec_verify.py: build each candidate program, keep the best valid,
fuse/repair otherwise); v2 = dx + geometry fixes; v3 = v2 + precise extents; trim = v3 +
silhouette trim as an extra exec-verify variant. v2, v3, trim: three seeds each.
Results (post-recovery, frozen analysis script bench/analysis/v2_dev.py; results/heldout/):
- Gated IoU over 300: d0 0.7975 (valid 259/300), dx 0.9012 (293/300), v2 0.9296 (3-seed),
  v3 0.9359 (3-seed, 298/300 valid), trim 0.9450 (3-seed).  [h2_primary_local.json,
  h2_secondary_local_no_section.json]
- PRIMARY dx − d0: +0.1037 [+0.0709, +0.1376], 43 better / 4 worse, Holm p < 1e-4.
- Secondary (Holm over 3 shown; the 4th, trim − section-only, is PENDING): v2 − dx +0.0284
  [+0.0127, +0.0465] 57/20 p_holm 1e-4; v3 − v2 +0.0063 [+0.0005, +0.0127] 69/38 p_holm 0.0035;
  trim − v3 +0.0091 [+0.0048, +0.0134] 90/1 p_holm < 1e-4.
- Sensitivity, original pre-recovery files (results/heldout_pre_recovery/,
  h2_primary_pre_recovery_local.json): dx − d0 = −0.7951 — entirely the 299 sandbox-setup
  failures of dx's original scoring (dx valid 1/300). Reported side by side.
- Recovery amendment (post-outcome measurement amendment, dated 2026-11-05): replay failures of
  class setup (sandbox) or resource (rc −9 / 900 s timeout) got one terminal recovery pass, same
  judge and limit, in all 8 runs; 531 eligible (299 dx setup, 222 v2-seed2 timeouts, 10 d0
  resource). d0's 10 failed again (stay 0); dx and v2-seed2 recovered (dx 293/300 valid; v2-seed2
  298/300). One dx recovery job ran on a faulty node and was cancelled before writing results.
- Trim caveats: the trim variant includes a second fuse/repair pass before trimming (seed-2
  00057691: 0.883 before trim from repair alone); one seed-0 trim replay timeout (00403399) kept
  as frozen 0. Decomposition (gated_no_trim, all 300 parts): second fuse/repair pass alone
  −0.0031 / +0.0000 / +0.0029 (seeds 0/1/2; seed 0 negative from the 00403399 timeout); trim
  proper +0.0089 / +0.0089 / +0.0096; total +0.0058 / +0.0089 / +0.0126.
- Runtime (results/heldout/h2_timing_summary.json; 3 parts per node in parallel, CPU only):
  mean/median min per part — d0 7.5/3.7, dx 16.0/5.5, v2 12.6–14.4/6.2–6.6, v3 14.6–15.6/7.1–7.3;
  totals 38 h (d0) to 78 h (v3) per 300-part run. Reserved 40: v3 mean 9.7–10.9 min.
- PENDING (ORCD): section-only control (h2_section_control.json), independent rejudge (seed 1,
  4x samples), surface agreement on the fused boundary, official stats outputs.
- Development history (not evidence for held-out claims): dev5/dev7 results in results/,
  AUTO_REVIEW.md (e.g. dev7 three-seed v3 − v2 +0.0087; trim +0.0050 15 better/0 worse).

## Study 2 — closed models on the 40 reserved fresh2 parts
Harness (agent/agent_loop.py, tools v2, CADFIT_AGENT_EXEC=1): every model change is executed and
judged; delivered answer = best executed valid program. Toolsets: "code" = describe_target,
section, evaluate, add_code, remove_step, list_steps, finish (geometric observations + execution
feedback — not an unaided LLM); "skills" adds CADFit stages (detect_directions, extract_sketch,
fit_extrude, fit_revolve, section_extrude, candidates). Budget 40 calls / 30 min; Claude via the
Anthropic Messages API (agent/anthropic_chat.py): adaptive thinking, effort high, 32k max tokens
per turn, full native history, no server fallbacks. Three independent episodes per part;
every delivered program re-judged offline by score.py's CAD replay.
Results (results/closed/closed_vs_pipeline.json; repeats averaged within part):
- Opus/code 0.9749 [0.9646, 0.9837], valid 120/120, mean 6.9 min, $0.275/episode
- Opus/skills 0.9411 [0.8778, 0.9861], 115/120 (5 no-output), 9.3 min, $0.164
- Sonnet/code 0.9455 [0.9314, 0.9588], 120/120, 5.0 min, $0.152
- Sonnet/skills 0.9323 [0.8767, 0.9654], 117/120 (3 no-output), 4.7 min, $0.088
- Pipeline on the same 40: d0 0.7792, dx 0.9340, v2 0.9515, v3 0.9512, trim (3 seeds) 0.9582.
- Opus/code − v3 +0.0236 [+0.0029, +0.0478] 25/15; − trim +0.0167 [−0.0013, +0.0364] 22/18.
  Opus/code − Sonnet/code +0.0294 [+0.0179, +0.0417] 37/2. Skills − code: Opus −0.0338
  [−0.0970, +0.0093]; Sonnet −0.0133 [−0.0683, +0.0198] (exploratory, 12+ comparisons).
- All 472 delivered programs valid; the 8 failures are no-output deadline episodes on 3 parts
  (00867782 all six skills episodes; 00300195, 00928992 one Opus-skills each). Earlier
  "all agents invalid" readings of 00560247/00928992 were verification timeouts; offline replay
  shows valid deliveries (e.g. Sonnet/code 00560247 0.947).
- Tool time (results/closed/agentsk_f2_tool_seconds.json): add_code 84–89% of code-arm tool
  time; skills arm dominated by extract_sketch / fit_extrude / add_candidate; single calls up to
  ~1,770 s. Model (API) time 8–19% of episode time.
- Discarded run: first Opus run on node4002 — 43/44 episodes with 90 s executed-call timeouts
  (578 total), $8.95; set aside (agentsk_f2/opus55_node4002_failed/diagnosis.json), rerun;
  preflight added.

## Study 3 — tools v3 (review-stage/TOOLS_V3_PROTOCOL.md, frozen before runs)
Changes developed and checked only on development parts (bench/profile_tools.py):
exact — KD-tree duplicate removal in profile fitting (identical on 300 random cases), O(1)
running-sum line error with exact SVD fallback near thresholds (identical on all 162 dev
sketches; fitting 559 s → 19 s), vectorized revolve rotation (bit-identical; fit_revolve
11.7 → 1.2 s), target loaded once per process in the judge (18/18 identical); behavioural — a
120 s cap per executed check, unchecked steps never delivered while a checked valid program exists.
Design: {v2, v3 frozen trees} × {code, skills} × {Opus, Sonnet} × 40 fresh3 parts × 3 episodes
= 960 episodes; delivered programs re-judged offline. Execution log: API credit exhaustion and
rate limits mid-run (239 episodes ended on API errors, moved aside, rerun); one node preflight
stop (53 episodes) and one deadline ReadTimeout crash, rerun. Final 960/960.
Results (results/tools_v3/tools_v3.json):
- Opus code v2 0.9730 [0.9544, 0.9847] 119/120 7.3 min | Opus skills v2 0.9503 [0.8908, 0.9862]
  116/120 8.9 min | Opus code v3 0.9838 [0.9786, 0.9884] 120/120 5.3 min | Opus skills v3 0.9870
  [0.9825, 0.9906] 120/120 4.2 min. Sonnet: code v2 0.9486, skills v2 0.9376 (3 no-output),
  code v3 0.9445, skills v3 0.9687 [0.9605, 0.9760] 120/120, 2.6 min.
- PRIMARY Opus skills v3 − v2: +0.0367 [+0.0018, +0.0957], 22/12, sign p 0.121, Holm 0.243 —
  NOT significant by the declared test.
- Opus skills v3 − code v3: +0.0032 [+0.0004, +0.0064], 28/11, Holm 0.028 (significant, small).
- Opus code v3 − v2: +0.0108 [+0.0007, +0.0285], 21/18, Holm 0.749.
- Sonnet (secondary, uncorrected): skills v3 − code v3 +0.0242 [+0.0097, +0.0447] 28/12 p 0.017;
  skills v3 − v2 +0.0311 [−0.0014, +0.0837] p 0.86; code v3 − v2 −0.0042 [−0.0088, −0.0002] p 0.50.
- Time (descriptive): Opus skills −4.70 min/part [−6.58, −2.93], faster on 33/40, sign p 1.4e-5;
  other cells −1.7 to −2.3 min with bootstrap intervals excluding 0 but sign tests not significant.
- Replication: Opus code v2 on fresh3 0.973 vs 0.975 on fresh2.

## Figures available (bench/figures/v2_2026-10-23/)
simple_closed_models.png (Study 2), simple_tools_v3.png (Study 3), detail_00642725.png /
detail_00232213.png (input mesh → broken program → repaired program → detail map; development
parts), simple_runtime.png, simple_results.png, pipeline_v2.png. Held-out pipeline figure: to make.

## Limitations to state
Post-outcome recovery amendment; infrastructure exclusions/reruns (node faults, API credit/rate
limits); 40-part agent cohorts (power for < 0.01 effects limited); fresh2's other 260 parts were
seen in pipeline outcomes (fresh3 is the clean cohort); the code baseline includes target
inspection and execution feedback; Claude settings (32k tokens/turn, full history) differ from the
open-model harness; one benchmark (CADBench hard tier, two splits); IoU-centric endpoint (surface
agreement pending); closed-model results tied to specific model versions and API.

Score: 4/10
Verdict: not ready

**There is genuine engineering progress, but the current artifacts do not establish the paper’s three intended claims: improved validity-gated CAD fidelity, improved surface detail, and better time efficiency. Keep fresh2 held out for now.**

I recalculated the supplied results, inspected the current implementation, and ran in-memory geometry probes. The dev3/dev4 reconstruction folders and agent transcripts are absent locally, so I could verify their score arithmetic but not replay those entire studies. Full pytest was blocked by the read-only environment’s cache restrictions; isolated probes did run.

Several previous concerns were genuinely addressed:

- Execution caching now uses program text, eliminating the demonstrated object-ID aliasing. Answer composition metadata uses the delivered answer.
- `exec_verify.choose()` now always prefers a valid program. My valid-versus-invalid selection probe passed.
- The new deadline exception survives ordinary `except Exception` handlers; the isolated interruption probe passed. Candidate execution now cleans up its process group on interruption.
- The stored oversized-circle revolve failure is now rejected.
- **The repair result is real:** executing the saved `00232213` programs changed an invalid shape containing two invalid solids into a valid shape with no invalid solids and essentially unchanged volume.
- The unsupported “tools rather than planning explain the gains” inference has been removed.
- fresh2 has 300 distinct parts, balanced 150/150, with no overlap against the other local manifests—including by source-part prefix.

Those are substantive fixes, not cosmetic responses.

1. **The latest effectiveness numbers still cannot support a clean causal claim.**

   Recomputed directly from [dev34_scores.json](/Users/Andrewlin/CADFit/results/dev34_scores.json):

   | Run | Mean validity-gated CAD IoU | Valid deliveries |
   |---|---:|---:|
   | dev3_d0 | 0.80798 | 52/60 |
   | dev4_dx | 0.91998 | 58/60 |
   | dev4_v2 | 0.94892 | 59/60 |

   These are **old-judge development results**, spanning code revisions and unstable execution outcomes. Approximately **79% of the d0→v2 gated improvement comes from parts where d0 did not deliver valid CAD**. Validity recovery is valuable; this decomposition does not invalidate it. It does prevent presenting the gain as primarily better geometric reconstruction.

   The additional v2−dx improvement is **0.02894**, with an exploratory paired bootstrap interval approximately **[−0.0013, 0.0744]**. The current evidence therefore does not establish that the geometry-fix package improves the mean beyond execution verification, rewriting, repair, and fallback selection.

   The paper also remains centered on the older A–D experiment. Its original held-out status can be described historically, but this same cohort is now development data for v2. Moreover, [numbers.tex](/Users/Andrewlin/CADFit/paper/numbers.tex:400) still contains pending controls and repeats that the prose describes as completed.

   **Minimum fix:** finish the complete, controlled dev5 matrix under common infrastructure and the corrected judge; rescore historical outputs; retain programs, replay records, and execution logs. Rewrite the manuscript around the resulting evidence and distinguish historical evaluation from subsequent development. Do not retrospectively exclude OOM failures: use a consistent retry/resource policy across arms and retain unresolved failures as zeros.

   Before final analysis, explicitly check manifest completeness. [score_runs()](/Users/Andrewlin/CADFit/bench/score.py:288) now correctly counts never-started parts within a recognized run, but still omits actively running parts and summarizes the common subset. That output is useful for monitoring, not automatically a completed experiment.

2. **The top-venue contribution remains insufficiently differentiated.**

   Executing proposals, using geometric feedback, and protecting a valid incumbent are already central to [CADFather](https://arxiv.org/html/2610.09127v1). Kernel-level validity feedback is also present in [CADSmith](https://arxiv.org/html/2603.26512v1). Neither “execute the program” nor “give an LLM CAD tools” is independently a convincing methodological novelty claim.

   The potentially valuable contribution is narrower: **a controlled demonstration of how mesh-based optimization misrepresents delivered CAD, which interventions repair that discrepancy, and what an LLM contributes beyond inexpensive geometric policies.** The decisive controls for that story remain unfinished.

   **Minimum fix:** choose that focused scientific question and complete its controls. Separate the execution/repair package from additional geometry changes, and include the cheap section-only/best-of control. If claiming competitive reconstruction performance, add a contemporary external method such as CADFather under your evaluator. If keeping this strictly an audit of one optimizer family, narrow the claims accordingly; that is presently a more plausible workshop/tooling paper than a strong NeurIPS/ICML submission.

3. **The agent study does not yet identify the benefit of the full tools or of LLM decisions.**

   The historical skills-versus-code result is substantial. However:

   - Code+section-only attribution remains pending.
   - The corrected shared-interface scripted-policy result remains pending.
   - Repeated episodes remain pending in the manuscript.
   - The six-model results concern the earlier tool/harness configuration.
   - Qwen3.8’s large sensitivity to its token allowance shows that harness configuration materially affects the comparison.

   The revised narrative correctly treats the nonsignificant agent–policy comparison as inconclusive. Preserve that restraint: it establishes neither equivalence nor absence of a planning contribution.

   **Minimum fix:** on the corrected common harness, compare **code, code+section, full skills, and the shared-interface deterministic policy**. Start with the strongest relevant open model before multiplying model configurations. Use repeated episodes and report validity-gated scores. Opus/Sonnet should extend this controlled comparison after development calibration; their presence alone will not repair the missing attribution.

4. **Execution feedback and recovery are still only partially aligned with the advertised objective.**

   In [CadWorkspace._exec()](/Users/Andrewlin/CADFit/agent/cad_tools.py:290), a successful manifold conversion is scored with `self._score(m)`. The corrected `score.robust_iou()` is reached only when that conversion fails. Since `_cached_manifold()` can repair or alpha-wrap geometry, this is not generally the same objective as the independent judge. Consequently, the executor log’s assertion that the judge correction also fixes agent feedback is too broad.

   I am **not** claiming the previous 0.13 discrepancy necessarily persists in agents. On `00966049`, I verified that the agent’s target conversion successfully repairs the cracks and agrees essentially exactly with the normalized STEP tessellation. The confirmed issue is the inconsistent scoring path, not an established new aggregate regression.

   Two earlier limitations also remain:

   - Agent `section()` still displays the mesh composition, whereas `evaluate()` can describe executed geometry.
   - Pipeline verification remains a final-stage shortlist operation. [Early analysis failure returns before verification](/Users/Andrewlin/CADFit/run_pipeline.py:1075), so adding late alternatives does not implement an incumbent that survives search failure. Refinement residuals also still originate from the decimated input.

   **Minimum fix:** use the declared executed-CAD criterion for authoritative answer selection, or explicitly label the internal score as a surrogate and avoid external-score guarantees. Make model-section feedback describe the same geometry. Either retain an executed fallback before expensive search, or accurately describe the method as final-stage verification with possible no-output failures. The latter is scientifically acceptable when failures remain in the denominator.

5. **The runtime evidence supports trade-offs, not a general efficiency advantage.**

   From [runtime_raw.json](/Users/Andrewlin/CADFit/results/runtime_raw.json), mean minutes on the same 20 parts are:

   | Configuration | Basic tools | CADFit tools |
   |---|---:|---:|
   | Gemma-4-31B | 27.69 | 19.41 |
   | Qwen3.6-35B | 5.62 | 5.58 |
   | gpt-oss-20b | 4.92 | 5.53 |
   | Qwen3.8-27B | 18.92 | 24.11 |

   The dev4_v2 pipeline averages **8.70 minutes** on those parts. Thus tools sometimes reduce elapsed time and sometimes increase it; the pipeline is not universally faster than agents.

   More importantly, [the agent runner defaults to eight simultaneous episodes sharing one model server](/Users/Andrewlin/CADFit/bench/agentsk_run.py). Episode latency therefore includes contention. Pipeline runs use another concurrency/resource configuration. These measurements are valid observations of those deployments, but not hardware-neutral algorithmic speed comparisons.

   The new setup/model/tool instrumentation is useful, but those fields are absent from the supplied historical timing records. One historical Gemma code episode also lasted **34.16 minutes**, so “30-minute cap” requires qualification.

   **Minimum fix:** measure the final configurations with declared hardware and concurrency. Report latency separately from throughput; include setup, geometry tools, execution verification, and answer delivery. Pair quality with time, report medians and tails, and count failed-attempt time. Use quality-versus-time curves or time to a prespecified quality target for an efficiency claim. Report API cost separately for closed models.

6. **“Detail recovered” currently conflates valid delivery with finer geometric fidelity.**

   The detail results are informative, but their strongest interpretation is narrower than the label.

   On the **52 parts valid in both runs**, I obtain:

   | Surface metric | d0 | v2 |
   |---|---:|---:|
   | Target surface within 0.5% of part size | 0.98225 | 0.98153 |
   | CAD surface within that tolerance of target | 0.92064 | 0.94079 |
   | F-score | 0.94671 | 0.95812 |

   The all-part gated recall rises **0.85128→0.96421**, but essentially all that increase comes from newly valid deliveries. Conditional recall does not improve. There is a legitimate smaller improvement in surface precision and F-score.

   A one-sided proximity threshold also does not establish that particular pockets, ribs, or shallow features were reconstructed. The actual v2 result for `00046097` illustrates why both directions matter: recall is **0.889**, but precision is only **0.492**.

   **Minimum fix:** call this *surface agreement at a stated tolerance*, and report recall, precision, and F-score together. Keep all-part gated results primary and common-valid comparisons explicitly diagnostic. Add a small prespecified tolerance sweep and sampling/tessellation convergence check. Stronger claims about recovering fine features need feature-sensitive evidence; otherwise narrow the wording.

**Of the planned method changes:**

| Change | Recommendation for this paper |
|---|---|
| Snap extrusion extents to detected planes | **Highest priority.** It directly addresses dimensions poorly resolved by the current translation grid. Use original-input planes and retain the unsnapped alternative until executed scoring selects between them. |
| Restrict translation search to the part extent and refine coarse-to-fine | **Worth doing.** A plausible accuracy/runtime improvement. Compare candidate quality, final gated score, and time against the existing sweep. |
| Silhouette trimming | **A development experiment, not yet a required ingredient.** Use actual projected silhouettes; extruding a middle cross-section can remove legitimate off-section material. Execute and validate the trimmed candidate, retaining the incumbent. |
| Occupancy-bitset IoU | **Defer unless profiling identifies composition scoring as a major bottleneck.** It changes the search approximation. Any speed claim needs resolution/seed convergence and independent final CAD scoring, particularly on thin parts. |

An early valid fallback is more directly motivated by the observed failure pattern than adding another approximate search objective.

**The final evaluation protocol should be:**

- **Development first:** complete dev5, settle judge/feedback semantics, finish the essential controls, and select any method changes using the existing 60 parts. No fresh2 outcome inspection during this process.
- **Freeze the actual experiment:** source, arm definitions, model identifiers/settings, budgets, resources, and retry rules. Ensure the d0 source includes the intended common infrastructure fixes; the current submission script still defaults to the older d0 revision.
- **Pipeline:** run the paired 300-part cohort, reporting the two splits separately and the balanced aggregate. Include d0, dx, v2, and a cheap executed section/best-of reference. First repeat development stress cases under several fixed seeds/runs. If material run variability remains, repeat the final comparisons; one seed cannot support claims of run robustness.
- **Agents:** prespecify a stratified subset and use at least three independent episodes per stochastic condition. Twenty parts can detect the large historical tools effect but may poorly resolve agent-versus-policy differences. Choose additional parts from a power/precision calculation on development data; more episodes do not substitute for more independent parts.
- **Statistics:** make mean validity-gated CAD IoU primary, with every attempted part represented. Use paired, split-stratified intervals, keeping all episodes of a part together. Report paired validity changes and prespecify the primary comparison family. Treat superiority and equivalence as different hypotheses.
- **Measurement:** retain judge method, union-sample count, and uncertainty. Check small claimed differences with higher-precision evaluation and independent sampling. State the occupancy convention for open targets—the current development cohort contains five, despite the draft’s watertight-input description.
- **Timing and detail:** evaluate the same final programs and configurations used for the quality claims. Publish the programs and replayable records underlying the tables.

**No go for fresh2 yet.** The release condition is a complete, interpretable development experiment with the final measurement protocol—not implementation of every proposed enhancement.

## Memory Update

- Confirmed fixed: object-ID execution-cache aliasing, invalid-preference selection, delivered-answer composition metadata, ordinary-handler swallowing of session deadlines, candidate-process cleanup path, and rejection of the stored oversized-circle revolve failure.
- Independently replayed `00232213`: original invalid with two invalid solids; repaired valid with essentially unchanged volume.
- Recomputed old-judge gated means: d0 **0.80798**, dx **0.91998**, v2 **0.94892**. Approximately **79%** of d0→v2 improvement comes from newly valid deliveries; v2−dx remains inconclusive.
- Surface recall is unchanged on common-valid parts; surface precision and F-score improve modestly. Gated recall improvement primarily measures validity recovery.
- Remaining implementation limitations: agent execution scoring bypasses the corrected judge on its normal path; model sections can show different geometry from execution feedback; pipeline fallback verification remains late.
- Remaining evidence gaps: complete dev5, corrected rescoring, matched policy, section-only attribution, repeated agent episodes, final-configuration timing, and locally available full reconstruction/trajectory artifacts.
- fresh2 remains balanced and disjoint. Keep outcomes untouched until the development validation and experiment freeze are complete.
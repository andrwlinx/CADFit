Score: 4/10
Verdict: not ready

**Hold the held-out evaluation until the defects below are fixed.** There is real progress, including a documented valid reconstruction rescue, but v2 still has reproducible correctness failures and an unfinished evaluation path.

I inspected the supplied diff, implementation, paper sources, and raw results. I used in-memory probes, including actual CadQuery execution; the read-only workspace prevented a full pipeline or pytest rerun.

1. **The agent’s execution cache can return another model’s result.**

   [CadWorkspace._exec()](/Users/Andrewlin/CADFit/agent/cad_tools.py:238) keys its cache by `tuple(id(s) for s in steps)`. Removing a step frees its dictionary; Python can immediately reuse that address for a different step. The cache retains the address, not the object.

   I reproduced this through the actual `add_code → remove_step → add_code` methods, mocking only replay/I/O and supplying controlled scores:

   - Base: executed score 0.90.
   - Rejected trial: executed score 0.10.
   - Remove trial, add an improvement with score 0.99.
   - The new step reuses the old ID. Its returned `program_iou` is **0.10**, and no replay occurs. The retained executed answer remains 0.90.

   This corrupts feedback and can suppress improvements during ordinary exploration. Separately, [episode metadata](/Users/Andrewlin/CADFit/agent/agent_loop.py:472) reports steps and sources from `ws.best`, although v2 exports `ws.best_exec`; reported program composition can therefore describe a different answer.

   **Minimum fix:** assign each added step a monotonically increasing identifier and use those identifiers for caching. Generate answer metadata from the selected executed answer. Add the add/remove/add regression above. The lexicographic **validity-first best-answer comparison itself is correct**; its cache inputs are not reliable.

2. **Pipeline selection explicitly contradicts the validity-gated objective.**

   [exec_verify.choose()](/Users/Andrewlin/CADFit/exec_verify.py:141) selects an invalid program whenever its IoU exceeds the best valid program by more than 0.005. A valid 0.90 reconstruction loses to an invalid 0.99 reconstruction, turning a primary score of 0.90 into **zero**.

   This is an intentional rule, not an obscure numerical case. It also contradicts the pipeline flag’s “best valid” description. **None of the eight completed local v2 records exercised this branch**, so I am identifying a demonstrated selection-rule defect, not claiming an observed aggregate regression.

   The failure path also weakens the delivery guarantee: when verification finds no built program or raises, [run_pipeline.py](/Users/Andrewlin/CADFit/run_pipeline.py:1317) leaves the previous mesh/program pair and mesh score in place. An independent `--cad` evaluation can catch this; `final_iou.json` alone cannot certify execution-verified delivery.

   **Minimum fix:** always prefer the highest-scoring valid program when one exists. If none exists, explicitly record a failed validity-gated result; keep diagnostic meshes separately identified.

   **What is correct:** comparing candidates with the target mesh is **not target leakage** here—the mesh is the reconstruction input. On successful selection, the pipeline copies the chosen program and its executed tessellation. Fused rewrites and skipped failed cuts are legitimate alternative candidates when their resulting geometry is actually scored.

   There is concrete positive evidence: the saved [00642725 verification record](/Users/Andrewlin/CADFit/bench/runs/dev2_v2/00642725_384f51542e8a1ea67d2847ef_step_003/final_iou.json:12) reports an original program with 208 solids, 34 invalid, and IoU 0.000898; the fused variant has one valid solid and IoU **0.937546**. That supports this repair on one case.

3. **The deadline implementation still fails, and the comparison changes stopping behavior along with tools.**

   The new [SIGALRM wrapper](/Users/Andrewlin/CADFit/agent/agent_loop.py:308) does not establish the claimed deadline:

   - [Axis refinement catches `Exception`](/Users/Andrewlin/CADFit/greedy_search.py:305), including the alarm’s `TimeoutError`, and continues. With injected delays in this real path, a 0.02-second deadline returned successfully after 0.144 seconds. The one-shot alarm had already been consumed.
   - During [candidate subprocess execution](/Users/Andrewlin/CADFit/cadquery_ops.py:661), cleanup handles `subprocess.TimeoutExpired`, but not the propagated alarm exception. A controlled probe returned a session-timeout error while its child process remained alive. I explicitly terminated that probe child.
   - [The scripted policy](/Users/Andrewlin/CADFit/agent/scripted_skills_policy.py:51) neither sets `ws.deadline` nor uses the new tool deadline wrapper. Its time limit remains a check between calls.
   - The policy’s v2 acceptance decision still uses mesh `iou_after − iou_before`, checking executed validity but ignoring executed-IoU improvement.

   **Minimum fix:** propagate session timeout exceptions through the relevant geometry handlers; clean up candidate processes on every interrupted exit; enforce the same remaining deadline for agents and policy. Under v2, make policy acceptance use executed-program quality.

   **The nudge reset is correctly implemented.** However, `CADFIT_AGENT_EXEC` changes feedback, assembly, answer selection, prompting, nudge behavior, and timeout handling together. That comparison measures the **whole v2 configuration**. To attribute gains specifically to tools, use the same corrected harness in both conditions; otherwise label the package comparison honestly.

4. **The revolve-origin correction is right; the new “deepest crossing” safeguard is incomplete.**

   Subtracting the plane origin before transforming the world-space axis is correct. The subsequent [emission check](/Users/Andrewlin/CADFit/cadquery_ops.py:466), however, examines selected coordinate pairs extracted by regex. It ignores circle radii, arc endpoints beyond the first pair, and curve extrema. It therefore cannot guarantee that the emitted profile lies on one side of the axis.

   This occurs in a saved v2 proposal, not merely a synthetic construction. In [00941601’s refinement, sketch 9](/Users/Andrewlin/CADFit/bench/runs/dev2_v2/00941601_071d956501ffc009e947b4d3_step_000/refine_under_1/precomputed_operations.json:7879):

   - Circle center x: **112.98129**
   - Radius: **112.68804**
   - Leftmost x: **0.29325**
   - Emitted vertical axis x: **0.294312**

   The circle crosses the axis by **0.001062**. Executing the emitted program produced `Standard_Failure: BRep_API: command not done`. Moving the axis outside the actual circle made it build, but produced a gigantic solid—volume approximately **28.25 million** in normalized coordinates. That is evidence of a bad fitted profile, not a useful candidate to rescue by moving its axis.

   **Minimum fix:** check the actual emitted curves, including their extrema. Restrict axis adjustment to numerical tolerance; refit or reject profiles requiring substantive alteration. Add this stored failure and a rotated, translated shaft regression. The existing offset-shaft test checks reported axis metadata and precision; it does not establish correctness of all emitted axes.

5. **The held-out cohort is sound, but the evaluation is not yet runnable and fully controlled.**

   Several checks pass:

   - Every stored top-level Python file in `dev2_d0_code` matches `e260397`.
   - In the supplied commit diff, dx disables both revolve changes and otherwise adds execution verification to d0’s configuration. This isolates the **verification/rewrite/fallback package**, not verification alone.
   - fresh2 contains **300 files**, exactly **150 benchA + 150 benchE**, with no file-ID overlap against other local cohorts.
   - Seeded selection reproduces the downloaded file lists. The planned 20-part agent subset contains **8 benchA and 12 benchE**. Three episodes per condition is sensible; it remains 20 independent parts.

   But there are concrete problems before launch:

   **The agent scorer breaks on fresh2.** [agentsk_score.py](/Users/Andrewlin/CADFit/bench/agentsk_score.py:126) still loads `fresh_scores.json` and `fresh_section_control.json`. Its direct `sc[p]` lookup raises a `KeyError` for fresh2 IDs; I reproduced that lookup without inspecting held-out geometry.

   **The pipeline scorer can omit unstarted parts.** [score_runs()](/Users/Andrewlin/CADFit/bench/score.py:268) only records a missing reconstruction when its part directory exists. Parts never launched after an interrupted job can disappear from the denominator. The acknowledged partial local run illustrates why completion checks matter: I found **11 completed d0 records and eight completed v2 records**, not a completed paired cohort.

   **The source freeze is incomplete.** [v2_submit.sh](/Users/Andrewlin/CADFit/bench/v2_submit.sh:16) snapshots top-level pipeline modules, while agents and replay/judge code use the live checkout. During this review, an uncommitted `fit_primitives.py` arc correction appeared outside the supplied diff. Copying that into dx introduces a geometry change relative to d0. Existing snapshots, newly copied snapshots, and live agents would then use different code.

   **Minimum fix:** wire scoring to the actual h2 references; require results/status for the entire declared manifest before analysis; freeze the complete source used by jobs and scoring after repairs. Preserve dx’s intended intervention explicitly. Smoke-test the scoring path before spending held-out compute.

   Prespecify primary contrasts and multiplicity handling, bootstrap by part within split, and keep repeated episodes together. Preserve CAD scoring method and Monte Carlo uncertainty—the current verifier discards the judge’s method, and the CAD scorer retains only its scalar IoU.

6. **The strongest improvements and the paper’s central controls remain unfinished.**

   The current pipeline verifies a small final shortlist. It does not preserve the best valid executed incumbent throughout search, and an earlier stage failure can prevent verification altogether. Moreover, `--score-original` fixes the main search input, while [residual construction and refinement acceptance](/Users/Andrewlin/CADFit/run_pipeline.py:1081) still use the decimated mesh.

   The raw development results suggest the following priorities:

   - **Retain a valid fallback early.** Execute original-mesh section proposals and promising simple candidates before expensive composition. Preserve that incumbent through search failure. Recomputing the earlier diagnostic—substituting A only where D is invalid/unbuilt—raises D’s development validity-gated mean from **0.8563 to 0.9145**. This is diagnostic headroom, not an achievable-performance estimate.
   - **Make refinement and tool feedback consistent with executed geometry.** Use the original target for authoritative residuals and acceptance. Align model sections, reported scores, and selected-answer metadata. Report which assembly operation failed, rather than only a generic build failure.
   - **Repair proposal failures before widening search.** Thin-part sections, reliable small profiles, and rejection/refitting of malformed curves have direct evidence behind them. More beam width or more model calls currently spend compute around these defects.

   The paper still has [pending controls and repeats](/Users/Andrewlin/CADFit/paper/numbers.tex:400). The new submission script runs skills-only v1/v2 comparisons; it does not complete the code-versus-section-only-versus-full-skills attribution study. [NARRATIVE_REPORT.md](/Users/Andrewlin/CADFit/NARRATIVE_REPORT.md:128) also still concludes that tools rather than planning explain most gains from a nonsignificant agent-policy comparison. That inference is unsupported.

   **Minimum fix:** complete the focused controls with corrected tools and common budgets, or narrow the claims. Clearly separate historical pre-v2 findings from development repairs and future held-out results. The current evidence supports a useful implementation audit; it does not yet establish a convincing top-venue methodological contribution.

## Memory Update

- Confirmed new defects: execution-cache aliasing after step removal; invalid-preference verifier selection; swallowed deadline exceptions; surviving candidate subprocesses; unmatched policy deadlines; incomplete revolve curve-crossing checks; fresh2 agent-scoring `KeyError`.
- Verified improvements: world-to-local origin subtraction, original-input routing for main sections/scoring, consecutive-nudge reset, validity-first agent retention logic, and the recorded fused rescue of `00642725`.
- Verified controls at the supplied revision: d0 source matches `e260397`; dx disables revolve changes; fresh2 is balanced, complete, and ID-disjoint.
- Local v2 evidence remains eight completed, selection-biased records. No aggregate v2 efficacy conclusion is justified.
- Track the concurrent `fit_primitives.py` edit separately from the reviewed diff and existing snapshots.
- Next round: regression evidence for these defects, complete dev-cohort replay, corrected scoring/protocol, then frozen held-out evaluation. Keep fresh2 outcomes untouched during repairs.
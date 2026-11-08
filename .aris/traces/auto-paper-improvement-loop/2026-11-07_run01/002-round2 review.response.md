**Overall score: 5/10 — weak reject.**  
**Verdict: No, not yet ready for submission.**

I reviewed the current LaTeX, result macros, and all 12 pages of the compiled PDF. The red pending outputs are treated as declared, unfinished analyses—not errors to remove. :codex-file-citation{path="/Users/Andrewlin/CADFit/paper/main.pdf" purpose="source"}

**Summary.** The paper presents an empirical audit of CAD reconstruction using execution, solid validity, and geometric fidelity as a joint endpoint. Its strongest result is the optimizer’s improvement from 0.798 to 0.901 gated IoU through verified delivery; the agent studies also establish a small advantage for revised CADFit tools over code. Acceptance is currently limited by evaluation inconsistencies, confounded timing attribution, an unsupported numerical guarantee, and insufficiently precise positioning against prior execution-based CAD systems.

**Strengths, ranked**

- **A substantial, practically meaningful primary result.** The +0.1037 improvement on 300 parts addresses whether the delivered artifact actually works. Reporting the +0.0035 difference among mutually valid deliveries helps explain where the improvement comes from.
- **Thoughtful statistical design and unusually transparent reporting.** Pairing by part, averaging episodes before inference, stratified bootstrap intervals, declared comparison families, and original-versus-recovered results are valuable. The distinction between a mean-effect interval and a sign test is correctly explained.
- **A useful controlled toolset comparison.** Study 3 compares both packages and both toolsets on the same fresh cohort. The revised-package Opus tools-versus-code result, +0.0032 with Holm \(p=0.028\), supports the stated within-package advantage.
- **Concrete diagnosis rather than unexplained benchmark gains.** Failure classes, profiling, equivalence checks, and delivery logic give the experiments identifiable argumentative roles.
- **Generally clear quantitative presentation.** The principal figures expose uncertainty and unfavorable outcomes rather than hiding them.

**Weaknesses, ranked, with actionable fixes**

I found no clearly fatal **CRITICAL** defect. The following are **MAJOR**.

- **MAJOR — The strongest claims do not consistently identify the evaluation procedure that produced them.**  
  Study 1’s headline result uses a post-outcome recovery amendment affecting 531 records. The amendment is disclosed well in §4 and Appendix C, but the abstract emphasizes prospective specification without identifying the amended measurement. Separately, trim uses its own 600-second replay rather than the common 900-second offline replay. Thus, the optimizer ladder does not yet represent one fully uniform delivery evaluation. The pending geometric rejudge does not, by itself, resolve different execution procedures.

  **Fix:** Identify the primary result as measured after the recovery amendment in the abstract. Replay the saved trim programs under the common offline protocol and report all arms’ execution outcomes, including trim, together. Clearly distinguish sandbox setup failures from program resource failures: the statement that the original failures “were not evaluations” is too broad for the timeout category. Preserve the original and recovered numbers.

- **MAJOR — The headline speedup has an unresolved execution-environment confound.**  
  The observed reduction from 8.9 to 4.2 minutes is substantial. However, §6 states that reruns used three rather than eight episodes per node; the paper does not show how these reruns are distributed across conditions. Because latency also determines deadline failures and opportunities for revision, this can affect quality as well as time.

  **Fix:** Report hardware, concurrency, and rerun counts by experimental cell. Establish the timing contrast with matched concurrency, using a controlled rerun or an adequately populated matched subset. Until then, retain the exact observed timing result but distinguish that observation from attribution of the entire reduction to the package. No additional rewrite-versus-cap ablation is necessary if the claim remains explicitly about the combined package.

- **MAJOR — The opening and positioning blur several different notions of execution-based evaluation.**  
  The abstract’s general statement about how “mesh-to-CAD reconstructors are scored” exceeds the demonstrated scope and conflicts with the paper’s own discussion of systems that evaluate executed programs. The cited CADFit paper also describes kernel validation and reports an invalid-output metric. That does not establish independent replay of the final exported artifact, but it requires a more precise distinction than execution versus no execution. [CADFit paper](https://arxiv.org/html/2605.01171v3)

  **Fix:** Distinguish proposal validation, final exported-program replay, every-solid validity checking, and zero-inclusive fidelity aggregation. Make Table 1’s criteria explicit and substantiate its “n.r.” entries. Center the contribution on the artifact-level audit and measured repairs. The existing quantitative wording about **a beam-search configuration of CADFit** is appropriately scoped and should remain direct; it does not need additional hedges.

- **MAJOR — Appendix H asserts a floating-point guarantee that the derivation does not establish.**  
  The exact-arithmetic identity is sound, but \(Q-SS^\top/m\) and the subsequent eigenvalue subtraction can suffer cancellation. Checking whether the computed result lies within \(10^{-6}\) of a decision boundary does not prove that its error is smaller than that band. Consequently, “floating-point differences cannot flip a decision outside that band” is unsupported. The parenthetical identification of RMS distance with “the smallest singular value squared” also conflates quantities.

  **Fix:** State the relationships explicitly:
  \[
  \lambda_{\min}(C)=\sigma_{\min}^{2},
  \qquad
  \mathrm{RMS}=\sigma_{\min}/\sqrt m.
  \]
  Either provide an error bound and a fallback triggered by that bound, or limit the equivalence claim to the exact-arithmetic identity and the reported empirical checks. Include degenerate and nearly collinear inputs in numerical validation. This is a technical correction, not a tone edit.

- **MAJOR — Some central procedures remain ambiguous or absent from the submission.**  
  “Each candidate program is executed” in the main text sounds broader than Appendix G’s search program plus fused/cut rewrite. Appendix E describes delivery as always selecting a verified valid program, omitting §5’s unverified fallback. Exact agent prompts and tool schemas are absent, and the PDF lacks a complete eight-cell Study 3 results table.

  **Fix:** Add concise pseudocode defining the candidate set, repair order, scoring, timeout handling, and fallback. Make the appendix consistent with §5. Include prompts/tool schemas and an appendix table containing every Study 3 cell’s score, interval, validity, no-output count, and runtime. These are documentation and presentation fixes; they do not require new experimental arms.

**Claim calibration and narrative**

- **Keep the supported positive claims.** The +0.1037 delivery improvement, exploratory +0.024 Opus-versus-v3 result, and revised-tools +0.0032 advantage do not need “may,” “potentially,” or additional defensive qualifications.
- **Do not interpret the Study 3 statistics as contradictory.** Its positive mean interval and nonsignificant sign test concern different estimands. Preserve both. Conversely, neither establishes a significant primary sign-test result.
- **The pending fourth optimizer comparison does not justify weakening every existing increment.** Even a conservative four-test Bonferroni adjustment leaves the weakest available optimizer sign test below 0.05. Final adjusted values still need updating.
- **The abstract begins with the problem, but becomes a compressed experiment log.** It lists three incremental gains, then follows unsuccessful tools into profiling and revision, ending on the nonsignificant primary test. Retain that primary outcome, but shorten the intermediate ladder and organize around the two substantive findings: reliable delivery and tool utility under execution costs.
- **The introduction starts with workflow background.** Move the program-versus-scored-geometry discrepancy ahead of the designer/program/kernel description.
- **The discussion’s “cost more time than they returned in score until…” sentence should be replaced.** It compares unlike quantities and overgeneralizes across models: original Sonnet tools were faster than Sonnet code, whereas original Opus tools were slower. Report the model-specific outcomes neutrally. Do not manufacture a tradeoff to explain the Opus weakness.
- **Remove duplicated defensive clauses outside Limitations.** Examples include “so it is not an unaided language-model baseline” and the repeated statement that the package does not separate rewrites from the cap. The positive toolset definition and package description already establish those facts; keep the attribution limitation once in Limitations.
- **Other requested defects are largely absent.** I found no pervasive stacked hedges, no literal “we do not claim” refrain, and no conclusion introducing new self-negation. The experiments have recognizable argumentative duties; the problem is repetition and development chronology, not purposeless experimentation.
- **Minor consistency issues:** fix Limitations numbering, which places (viii) before (vii), and distinguish optimizer v2/v3 from tool-package v2/v3 wherever both could be read.

**Missing references**

The closest mesh-to-CAD systems are already cited. Two relevant additions to the agentic-CAD paragraph are:

- [CADSmith](https://arxiv.org/abs/2603.26512): programmatic OpenCASCADE measurements and nested execution/geometric correction loops.
- [RA-CAD](https://arxiv.org/abs/2608.05714): learned post-execution critique in an iterative CAD-generation loop.

These warrant brief positioning, not mandatory new baselines. The more consequential reference issue is accurately distinguishing the evaluation practices of the works already cited.

**Visual review**

| Aspect | Assessment and fix |
|---|---|
| **Figure quality** | Figures 1, 3, and 4 are readable, with clear intervals and useful marker distinctions. Figure 2’s fine geometry and annotations are too small to inspect confidently; enlarge a detail inset. |
| **Grayscale** | Circle/square markers and open/filled markers preserve the statistical plots’ meaning. Orange and green bars become similar gray tones. Figure 2’s invalid-solid highlighting and pale distance map lose substantial information; add direct annotations and a luminance-readable colorbar. |
| **Caption alignment** | Captions generally match their figures and clearly identify cohorts and aggregation. Figure 2 correctly labels its example as development data and its IoU as pipeline-recorded. Figure 1 covers Studies 1–2, although the introduction references it while announcing three findings. |
| **Layout** | No orphaned section headings or obvious clipping. However, Figure 2 and Table 2 interrupt the arms paragraph between “dx adds” and its continuation across pp. 3–4. Figure 4 and Table 4 similarly interrupt the package-description sentence across pp. 6–7. Reposition floats after complete paragraphs. |
| **Tables** | Columns and decimal precision are generally consistent. Table 1 is excessively reduced; Table 3 compresses two optimizer rows and intervals into slash-separated cells. Split those rows and shorten headers instead of shrinking the table. Best values are not bolded; modest emphasis would help, provided it does not imply significance. |
| **Consistency** | The blue optimizer, orange code, and green CADFit-tool scheme is consistent across the quantitative figures. Figure 2 uses a separate status/error palette that needs an explicit scale. Standardize IoU tick precision where practical. |

**Submission verdict: No.** The paper has a credible empirical contribution, but needs a common replay endpoint, defensible timing attribution, corrected numerical claims, and a more self-contained method description. Filling the declared pending analyses alone will not resolve those issues.

- :codex-followup[Create a revision checklist]{prompt="Turn this review into a prioritized revision checklist, separating manuscript fixes, analyses using existing records, and new controlled measurements."}
- :codex-followup[Revise the narrative]{prompt="Propose revised abstract, introduction, and discussion text addressing this review while preserving all facts, numbers, comparison directions, and statistical outcomes."}
- :codex-followup[Specify the validation plan]{prompt="Specify the minimum common-replay, matched-concurrency, and numerical-equivalence checks needed to resolve the major technical weaknesses in this review."}
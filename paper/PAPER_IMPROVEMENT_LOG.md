# Paper Improvement Log — Execute the Program

## Score Progression

| Round | Score | Verdict | Key Changes |
|-------|-------|---------|-------------|
| Round 0 (after claim-audit fixes) | 4/10 | No | Baseline for the loop |
| Round 1 | 5/10 | No | d0 correctly identified as our pre-repair beam-search configuration (not released CADFit); pending analyses described accurately (re-judging is geometric re-scoring, no common trim replay); package-level tool claims; judge/arm/rewrite methods appendix; Holm citation; positioning table by evaluation design; defensive phrasing removed; dot-and-interval figures with grayscale-safe markers; hidelinks; shorter title; 4-decimal contrasts |

## Round 1 Review (GPT-6-Astra xhigh, fresh thread 01a1b90e-bd8a-7113-92c4-9f0e0e0da828)
<details><summary>Verbatim review (round 1)</summary>

**1. Overall score: 4/10 — reject in its current form**

I read the listed LaTeX sources and result macros, visually inspected all 11 pages of the compiled PDF, and checked relevant protocol and implementation files. Red pending outputs are treated as known gaps, not formatting errors. PDF reviewed: :codex-file-citation{path="/Users/Andrewlin/CADFit/paper/main.pdf" purpose="source"}

The main reason for this score is a consequential baseline attribution error, followed by inconsistencies in the evaluation description. The numerical findings remain potentially valuable.

**2. Summary**

The paper audits mesh-to-CAD systems through executed, validity-gated outputs and studies how optimizer components behave as tools for language-model agents. Its strongest findings are the +0.104 improvement from execution-verified delivery on 300 parts and the revised tool package’s combination of lower observed runtime and a small, Holm-significant advantage over code-only tooling; however, the manuscript misidentifies its baseline and overstates what the experiments establish about the mechanism behind the tool gains.

**3. Strengths, ranked**

- **A consequential evaluation target.** Scoring the delivered program, retaining failed deliveries in the denominator, and checking individual solids addresses a practical failure mode that mesh similarity can conceal.

- **A substantial primary empirical effect.** The amended dx–d0 contrast is +0.104, with interval [+0.071, +0.138]. The much smaller +0.0035 difference on jointly valid outputs helps distinguish delivery reliability from geometric fidelity.

- **Strong experimental bookkeeping.** Frozen source trees, prospective comparisons, part-level pairing, within-part averaging, and explicit amendment records are valuable. Reporting the original, dramatically worse replay results alongside recovered results is particularly good practice.

- **Useful separation of delivery and verification.** The paper distinguishes offline validity from checks completed during an agent episode. This matters when evaluating systems with deadlines.

- **The paper preserves inconvenient findings.** It reports the unsuccessful primary sign test in Study 3, the negative Sonnet code-version contrast, deadline failures, and incomplete runtime accounting. These should remain visible.

**4. Weaknesses, ranked, with actionable fixes**

- **CRITICAL — The tested d0 baseline is incorrectly described as released CADFit.**

  Section 4 calls d0 the released pipeline with two common fixes. The committed [held-out protocol](/Users/Andrewlin/CADFit/review-stage/HELDOUT_PROTOCOL.md:30), however, identifies d0 as the **pre-v2 `beamsec` pipeline**. The [runner](/Users/Andrewlin/CADFit/bench/run_parallel_arms.sh:35) enables exact-union scoring, a cut phase, event slices, direction detection, beam width four, and section-extrusion proposals. The frozen `e260397` snapshot also describes default-on branch modifications beyond the released code.

  Consequently, “the released optimizer fails on 41/300 parts” is not established by this experiment as documented. This affects the abstract, introduction, Figure 1, Table 2, and interpretation of the primary contrast.

  **Fix:** Identify d0 consistently as the tested modified baseline and provide its upstream commit, branch commit, patches, and full configuration. Preserve the +0.104 result as an improvement over that baseline. If the paper retains a claim specifically about released CADFit, evaluate the actual release under explicitly documented common infrastructure changes. This is a factual correction, not a tone edit.

- **MAJOR — The promised common-protocol re-evaluation does not match the available rejudge implementation.**

  Section 4 says the pending independent rejudging will apply the common protocol to trim outputs, which currently use a 600-second replay limit instead of 900 seconds. But [bench/rejudge.py](/Users/Andrewlin/CADFit/bench/rejudge.py:9) reads saved executed tessellations, retains existing validity decisions, and recomputes IoU with another seed and more samples. It does **not** replay delivered programs or reconcile replay limits.

  The recovery amendment is transparently disclosed and is not inherently invalid. Nevertheless, setup failures and resource-limit failures have different interpretations, and the resulting endpoint needs one precise operational definition.

  **Fix:** Separate **program replay validation** from **higher-precision geometric rescoring**. Replay frozen delivered programs under the common sandbox, memory, timeout, and retry rules; independently rescore their resulting geometry. Keep original and amended outcomes. Retain the pending markers while these analyses run, but accurately identify what each pending analysis will establish.

- **MAJOR — The causal explanation for the tool gains exceeds the experimental identification.**

  Q3 asks whether the cause is geometry or computational cost. The introduction answers that the cost “was overhead,” and the discussion implies that removing it changed the conclusion about the tools. Yet tools v3 combines computational rewrites with a **behaviour-changing 120-second check cap**. The experiment identifies the effect of that package, not the contribution of either component.

  Profiling four development parts establishes a concrete bottleneck in sketch extraction. It does not establish that overhead alone caused the agent-quality difference. Furthermore, a sign reversal between Studies 2 and 3 is not itself an interaction test, because the cohorts differ.

  **Fix:** Describe the demonstrated result as a package-level finding. Keep the observed 8.9→4.2-minute reduction and the +0.003 tool-versus-code advantage without additional hedges. If mechanism attribution remains central, add rewrites-only and cap-only conditions under comparable execution conditions, and estimate the toolset-by-version interaction on the same cohort. Disclose timing sensitivity to the documented concurrency changes during reruns.

- **MAJOR — The judge and algorithmic changes are insufficiently self-contained.**

  The manuscript omits the Monte Carlo sample count, stopping rule, sampling domain, winding threshold, tessellation tolerance, and handling of overlapping solids. These details matter when a highlighted difference is approximately 0.003. “Computed exactly” also needs to identify the object: the tessellated polyhedral volumes, rather than the underlying analytic CAD solids.

  Likewise, “geometry fixes” does not explain v2 sufficiently. Calling four changes “exact rewrites” is stronger than demonstrating agreement on finite development tests, particularly for running-sum computations replacing SVD-based calculations.

  **Fix:** Add a compact methods appendix containing the metric definition, numerical settings, union semantics, arm-by-arm changes, and selection/repair pseudocode. Include the running-sum derivation and conditions for equivalence, or restrict the equivalence statement to the tested inputs while preserving the exact agreement counts. Include the actual prompts and tool schemas in the submitted supplement. This empirical paper does not need an unrelated theorem; it needs precise definitions and support for its exactness claims.

- **MAJOR — Positioning obscures the contribution relative to execution-aware prior work.**

  The introduction groups CAD agents under tools that return geometry rather than necessarily executable programs, citing CADFather. Yet CADFather explicitly executes proposed programs and preserves the best valid result, as the paper’s own related-work section acknowledges. [CADFather’s description](https://arxiv.org/abs/2610.09127) confirms this.

  Table 1 also compares “search scored on meshes” against “executed in evaluation,” mixing search objectives with final evaluation procedures. Its “Held-out, frozen” column bundles distinct properties and gives an ambiguous dash to prior work.

  **Fix:** Frame the contribution around the demonstrated audit findings, controlled repairs, and tool-package evaluation. Distinguish search scoring, final-program replay, validity gating, and prospective analysis in the positioning table. Use “not reported” where appropriate and specify which study satisfies which prospective-design criterion. A broader empirical claim would benefit from another system under the common judge; a clearly scoped audit does not require a wholesale leaderboard expansion.

- **MINOR — Statistical presentation sometimes conflates different questions.**

  The bootstrap intervals estimate mean differences; the sign tests assess the balance of positive and negative part differences. Thus +0.037 with interval [+0.002, +0.096] and primary sign-test \(p=0.121\) are not contradictory. Explain this once.

  Complete the declared four-test Holm family rather than displaying Holm over three available tests. This need not weaken the existing significance statements: from the reported counts, the largest raw \(p\) among those three is approximately 0.00353, which remains below 0.05 even under a conservative four-test Bonferroni adjustment.

- **MINOR — Terminology and scope could be clearer.**

  Optimizer v2/v3 and tool-package v2/v3 are different objects with easily confused names. Define benchA and benchE beyond their identifiers. The two fresh3 document-hash overlaps disclosed in Appendix A belong in the generalization limitations; they are not, by themselves, proof of leakage.

**5. Claim calibration and narrative review**

Several findings warrant direct language. The +0.104 tested contrast, the observed runtime reduction, and the +0.003 Holm-significant Opus comparison should not be buried under additional generic qualifications.

| Passage or pattern | Assessment and specific revision |
|---|---|
| “A frontier model with plain code matches the improved optimizer.” | “Matches” suggests equivalence, which was not tested, while understating the positive exploratory contrast against v3. State the two comparisons separately: +0.024 against v3, with nominal interval excluding zero; +0.017 against trim, with interval including zero. |
| “The difference is a failure tail, not worse programs.” | All delivered programs being valid does not establish equal geometric quality. Report the eight deadline/no-output failures directly. Support any stronger decomposition with paired fidelity results on common-success cases, explicitly labelled diagnostic. |
| “The largest … improvement … came from no new geometry at all.” | The dx procedure fuses, repairs, and can drop solids. “No new geometry” is too broad. Attribute the gain to the documented delivery-and-repair procedure; distinguish this from adding new proposal families. |
| “The optimizer’s stages first looked useless…” | This is defeat language and a progress-report narrative. Replace it with the measured Study 2 quality, delivery, runtime, and API-cost results. “Useless” is unsupported. |
| “We do not propose a new reconstructor…” | Self-defensive positioning. State the positive contribution—an audit and repair study of an existing reconstruction pipeline—while preserving that scope. |
| “We do not read it as evidence of no effect either.” | Generic statistical self-defence. Remove it from the results narrative; explain the mean-versus-sign-test distinction once. Keep the unsuccessful declared primary test explicit. |
| “No claim here depends on [pending outputs].” | Too sweeping. The promised common-protocol trim comparison and precision assurance for small effects do depend on relevant checks. Replace this with an exact statement of which results are current and what each pending analysis validates. |
| Discussion ending: “which part of the package matters was not isolated.” | The substantive conclusion ends with self-negation already covered in Limitations. Move that limitation there and end the discussion with the supported package-level finding. |

I do **not** see pervasive stacked hedges or literal “we do not address X” confessions. The dominant writing problems are defensive asides, causal overreach, and the retrospective “tools disappointed us, then we repaired them” storyline.

The abstract opens with the evaluation procedure rather than the concrete failure it addresses. The introduction is more problem-oriented, but delays the strongest result through protocol details and Q1–Q3. A better ordering is:

1. The gap between search geometry and a valid delivered program.
2. The execution-based audit and delivery intervention.
3. The strongest correctly attributed result.
4. Agent-tool findings, with the package comparison’s primary-test outcome stated neutrally.

Every main experiment has a plausible argumentative role. Make those roles explicit: the section-only control tests the value beyond a simple geometric reference; surface agreement tests whether volumetric gains preserve boundary fidelity; independent rescoring tests measurement stability. Figure 1(b) substantially duplicates Figure 3 and Table 3, so some presentation can be cut without removing evidence.

The Study 3 primary non-rejection must remain a result. It should neither become the paper’s organizing “defeat” nor be relabelled as a tradeoff. Preserve all unfavorable table entries.

**6. Missing references**

- Add **Holm (1979), “A Simple Sequentially Rejective Multiple Test Procedure,”** because the correction is central to the confirmatory claims. [Original paper](https://www.ime.usp.br/~abe/lista/pdf4R8xPVzCnX.pdf).
- The closest execution-aware CAD work is already cited. The more pressing issue is accurate positioning against those references, rather than adding a long citation list.

**7. Visual review**

| Aspect | Findings from the compiled PDF |
|---|---|
| **Figure 1, p. 2** | Clean and readable when enlarged, but category labels and invalid-count annotations are small at normal page size. The caption explains fractional counts and the truncated axes. Replace ambiguous “inv.” with a label covering all unsuccessful replay classes. Correct the “released” baseline label. Dot-and-interval plots would avoid exaggerating differences through truncated bars. |
| **Figure 2, p. 4** | The four-panel sequence supports the delivery-failure example. However, the almost uniformly red rendering does little to distinguish 34 invalid solids from the remaining solids. The distance panel lacks a conventional colorbar and a close-up that makes the detail claim inspectable. “Detail recovered” is less precise than a distance-map label. The caption correctly identifies a development example. |
| **Figure 3, p. 6** | Panels and caption align: score, runtime with hatched model time, and API cost. The optimizer reference is useful. In grayscale, orange and green become very similar shades; ordering helps, but is insufficient as the sole redundant encoding. Add direct labels or distinct outlines/patterns without confusing the existing runtime hatching. |
| **Figure 4, p. 7** | Readable and aligned with its caption. Purple and green retain somewhat better grayscale separation. The most important +0.003 paired comparison is difficult to see in marginal bars; annotate its paired estimate and test, or use a paired-difference panel. |
| **Color consistency** | Figures 1 and 3 consistently use orange for code and green for CADFit tools. Figure 4 reuses green for the new tool version, including code-only conditions. Legends explain this locally, but the semantic change is avoidable. |
| **Title and page flow** | The title occupies four lines, with “Use” alone on the last line. Figure 1 separates Q3 on p. 2 from Q1–Q2 on p. 1. Table 2 appears before Section 4 introduces its arms. Figure 4 and Table 4 precede the package and design definitions on p. 7. Reposition floats and shorten or reflow the title. |
| **Other layout** | No major clipping, overlapping objects, or orphaned section headers were evident. Figures remain reasonably close to the relevant sections. Several result paragraphs cross page boundaries around large float blocks, interrupting the argument. |
| **Tables** | Rules and columns are generally clean. Table 2 is considerably smaller than body text; long contrast rows compound the density. Separate outcome summaries from contrasts if needed. Decimal precision is mostly consistent, but endpoints such as `+0.000` and `−0.000` conceal meaningful signs; use four decimals for small-effect intervals. |
| **Best-result emphasis** | Best values are not bolded. That is acceptable for an audit rather than a leaderboard. If bold is introduced, define whether it marks numerical best or statistical support, and use it consistently. |
| **PDF styling** | Green citation boxes, red cross-reference boxes, and cyan URL boxes add visual clutter. Hide link borders while preserving clickable links. Keep the red pending outputs until their results are available. |

**8. Verdict: No**

The paper has a credible empirical core, but it is not ready for submission. Correct the baseline provenance first, reconcile replay versus rescoring, and align the tool-mechanism claims with the package-level evidence. Completing the known pending analyses and tightening the narrative could then make the contribution substantially more convincing.

- :codex-followup[Build a revision plan]{prompt="Turn this review into a prioritized revision checklist, separating factual corrections, analyses, writing changes, and visual fixes."}
- :codex-followup[Draft calibrated framing]{prompt="Draft a revised abstract, contribution list, and conclusion using the supported findings and corrected baseline attribution; preserve all numbers and statistical distinctions."}
- :codex-followup[Specify evaluation repairs]{prompt="Specify the concrete changes needed to separate uniform program replay from independent geometric rescoring, including the outputs needed for the paper."}

</details>

### Fixes implemented
1. CRITICAL d0 provenance: d0 = pre-repair CADFit configuration (exact union, cut phase, event slices, direction detection, beam 4, section proposals; commit e260397 + two infra patches); abstract, intro, Sec. 4, Fig. 1, tables, appendix (app:arms flags).
2. MAJOR replay vs rescoring: removed the claim that re-judging applies the common protocol to trim; stated that no common-protocol replay of trim programs was run; pending paragraph names what each pending analysis tests.
3. MAJOR causal scope: Q3/answers/discussion describe a package-level result; "overhead" causal phrasing removed; rerun concurrency noted.
4. MAJOR self-containedness: app:judge (normalization, exact path, MC sampling 40k batches to 10k union / 5 batches, winding threshold 0.5, tessellation tolerances), app:arms (flags, delivery procedure), app:rewrites (running-sum derivation, decision band); "exact rewrites" → "output-preserving rewrites" with test counts.
5. MAJOR positioning: Table 1 split into search scoring / final replay / validity gating / prospective design with n.r.; intro no longer lumps CADFather with geometry-only tools.
6. MINOR stats: interval vs sign test explained once (Sec. 3); Holm (1979) cited; contrasts at 4 decimals.
7. MINOR terminology: tool packages renamed original/revised (optimizer keeps d0/dx/v2/v3).
8. Narrative: "matches" replaced by the two comparisons; "failure tail" claim replaced by direct counts; "no new geometry" → delivery step; "first looked useless" removed; "we do not propose" and "we do not read it as evidence of no effect" removed; discussion ends on the supported finding, the unisolated-component caveat moved to Limitations; fresh3 hash overlap added to Limitations.
9. Visual: dot-and-interval plots (Fig. 1, 3, 4), marker shapes and outlines for grayscale, Fig. 4 colours by toolset with open/filled by package, "no valid replay" counts in tick labels, hidelinks, two-line title, wide tables scaled.

| Round 2 | (final; no third review by design) | — | trim common replay launched (placeholder); timing confound quantified (reruns per cell, first-launch-only contrast); abstract states amendment; positioning table criteria defined + CADSmith/RA-CAD; floating-point claim corrected; delivery procedure consistent; full Study 3 table; tool listing; narrative fixes |

## Round 2 Review (GPT-6-Astra xhigh, fresh thread 01a1b91a-75d0-7090-8e68-2a9c69dad5e9) — 5/10, No

<details><summary>Verbatim review (round 2)</summary>

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

</details>

### Fixes implemented
1. Abstract: primary result labelled as measured under the dated recovery amendment, shown beside the original; opening narrowed to optimization-based reconstructors; ladder shortened.
2. Trim on the common protocol: bench/trim_common_replay.py launched on ORCD for all three seeds (placeholder \hTrimCommon until it finishes).
3. Recovery wording: setup failures (no evaluation) distinguished from resource failures (machine or program).
4. Timing confound: reruns per cell (Table tab:tools-cells; 75 of 120 for Opus CADFit original vs 23 revised) and the Opus CADFit timing on first-launch episodes only (-3.9 min [-7.0, -1.0], 14/20 faster, p 0.12) reported in Sec. 6; Limitations note concurrency.
5. Positioning: Table 1 criteria defined in caption (search signal, final replay, zero-inclusive, prospective); CADFit row notes kernel validity reported; CADSmith and RA-CAD added (verified on arXiv).
6. Appendix H: floating-point guarantee removed; sigma_min relations stated; equivalence rests on the exact identity plus tests.
7. Procedures: dx candidate set stated (search program + fuse/cut rewrite); delivery fallback consistent between Sec. 5 and the appendix; full Study 3 table; tool listing with pointer to prompts/schemas in the supplement.
8. Narrative: intro opens on the gap; model-specific statement replaces the unlike-quantities sentence; duplicate defensive clauses removed; limitations numbering fixed.
9. Layout: optimizer rows in Table 3 split; floats [tb].

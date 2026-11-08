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

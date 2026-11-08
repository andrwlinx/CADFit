# Paper Improvement Log — Execute the Program

## Score Progression

| Round | Score | Verdict | Key Changes |
|-------|-------|---------|-------------|
| Round 0 (after claim-audit fixes) | 4/10 | No | Baseline for the loop |
| Round 1 | (round-2 review) | | d0 correctly identified as our pre-repair beam-search configuration (not released CADFit); pending analyses described accurately (re-judging is geometric re-scoring, no common trim replay); package-level tool claims; judge/arm/rewrite methods appendix; Holm citation; positioning table by evaluation design; defensive phrasing removed; dot-and-interval figures with grayscale-safe markers; hidelinks; shorter title; 4-decimal contrasts |

## Round 1 Review (GPT-6-Astra xhigh, fresh thread 01a1b90e-bd8a-7113-92c4-9f0e0e0da828)
Verbatim review: .aris/traces/auto-paper-improvement-loop/ (round 1).

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

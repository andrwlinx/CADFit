# Paper Writing Pipeline Report

**Input**: NARRATIVE_REPORT.md (rebuilt 2026-11-07) + results/
**Venue**: ICLR 2027
**Assurance**: draft
**Submission-ready**: no (preregistered outputs still running: section-only reference + 4th secondary test, geometric re-scoring, surface agreement, common-protocol trim replay)
**Forensics**: skipped (draft)
**Date**: 2026-11-08

## Pipeline Summary

| Phase | Status | Output |
|-------|--------|--------|
| 0. Assurance Setup | done | paper/.aris/assurance.txt = draft |
| 1. Paper Plan | done | PAPER_PLAN.md |
| 1.5 Acceptance Contract | accepted (2 rounds) | PAPER_ACCEPTANCE_CONTRACT.md |
| 2. Figures | done | hero.pdf, detail.png (dev example), closed.pdf, tools_v3.pdf |
| 3. LaTeX Writing | done | 10 section files, 24 bib keys cited; all results as generated macros (paper/numbers.tex) |
| 4. Compilation | done (tectonic) | paper/main.pdf, 13 pages (main text ends p. 8) |
| 4.7 Claim audit (round 0) | FAIL → fixed | numbers reproduced; reporting fixes |
| 5. Improvement | 4/10 → 5/10 → round-2 fixes applied | PAPER_IMPROVEMENT_LOG.md |
| 5.5 Claim audit (final) | WARN | PAPER_CLAIM_AUDIT.{md,json}: all 437 macros and every number reproduce |
| 5.6 Kill argument | skipped (draft, advisory) | — |
| 5.8 Citation audit | FAIL → 8 FIX applied (WARN, not re-audited) | CITATION_AUDIT.{md,json}: 22/22 cited works exist |

## Improvement Scores
| Round | Score | Key changes |
|---|---|---|
| 0 | 4/10 | baseline |
| 1 | 5/10 | d0 correctly identified (pre-repair beam-search configuration, not released CADFit); pending analyses scoped; package-level tool claims; methods appendix; dot-and-interval figures |
| 2 | (fixes applied) | amendment named in abstract; trim common replay launched; timing confound quantified; positioning criteria; floating-point claim corrected; full Study 3 table |

## Contract check (row 0)
All assertions satisfied except: A16 asked for "excludes every source model"; the evidence supports exclusion by model index only (two fresh3 parts share a document hash with fresh2 parts) — the paper states the narrower rule and discloses the overlap (Limitations viii, App. A). A5/A17 rely on visible placeholders for the running analyses, as the contract allows.

## Deliverables
- paper/main.pdf (= main_final.pdf), main_round0_original.pdf, main_round1.pdf, main_round2.pdf
- paper/PAPER_IMPROVEMENT_LOG.md (verbatim reviews), review_round1.md, review_round2.md
- paper/PAPER_CLAIM_AUDIT.{md,json}, paper/CITATION_AUDIT.{md,json}

## Remaining before submission
1. Fill the five pending macros when the ORCD jobs finish (section 28262092, rejudge 28032513, surface 28262094, trimcommon 28264424-26, stats 28262095): rerun `bench/paper_numbers.py`, recompile; the secondary family then becomes Holm over 4.
2. Re-run the citation audit once after the table fixes; re-run the claim audit after the pending numbers land.
3. Optional: matched-concurrency rerun for the tools-v3 timing contrast; enlarge Figure 2 detail with a colorbar.
4. Research review loop (run_20261105_105505a5) round 3 with the completed held-out statistics.

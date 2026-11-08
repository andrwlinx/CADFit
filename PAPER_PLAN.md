# Paper plan — Execute the Program (rebuilt 2026-11-07; source: NARRATIVE_REPORT.md)

Venue: ICLR 2027 (9 pages main text, unlimited appendix/references), anonymized.
Working title: **Execute the Program: An Execution-Based Audit of Mesh-to-CAD Reconstruction and
Agent Tool Use**

## Thesis (one sentence)
Judging mesh-to-CAD systems by the solid their delivered program actually builds changes what
works: execution-verified delivery is the largest single improvement to an optimizer, a frontier
LLM with plain code tools matches the improved optimizer, and an optimizer's stages help such an
agent only after their implementation cost is removed.

## Contributions (each maps to evidence)
C1 Execution-based evaluation protocol (sandboxed replay, per-solid OCC validity, robust judge,
   validity gating; frozen, prospectively specified studies with source-disjoint cohorts and
   dated amendments). Evidence: protocol docs, code.
C2 Held-out optimizer study: execution-verified delivery +0.104 (primary, preregistered); v2, v3,
   trim increments (secondary). Validity 259/300 → 298–300/300. Runtime cost reported.
C3 Closed-model agents under the same judge: Opus 5.5 + plain code 0.975, above optimizer v3 on
   the same 40 parts; optimizer stages as tools did not help and caused deadline failures.
C4 Profiled tool redesign evaluated on a fresh cohort: halves Opus+CADFit-tools time, removes
   no-output episodes, CADFit tools beat plain code by a small Holm-significant margin;
   primary (v3 vs v2) not significant.

## Claims–evidence matrix
| Claim | Evidence | Section |
|---|---|---|
| Released optimizer delivers non-building/invalid programs on 41/300 held-out parts | h2_primary_local (d0 valid 259/300) | 4 |
| Execution-verified delivery +0.104 [0.071, 0.138] | h2_primary_local | 4 |
| Geometry fixes +0.028, extents +0.006, trim +0.009, all Holm-significant (3 of 4 tests; 4th pending) | h2_secondary_local_no_section | 4 |
| Trim gain is trim proper (+0.009/seed), second repair pass ~0 | trim decomposition | 4 |
| Conclusions depend on the recovery amendment for dx (pre-recovery −0.795) — shown | h2_primary_pre_recovery_local | 4, App |
| Pipeline cost 7.5 (d0) → ~15 (v3) min/part mean | h2_timing_summary | 4 |
| Opus+code 0.975 > v3 0.951 on reserved 40 (+0.024 [0.003, 0.048]); vs trim not established | closed_vs_pipeline | 5 |
| CADFit-tool episodes fail by deadline, not by invalid programs (472/472 delivered valid) | agentsk_f2*_scores | 5 |
| Tool execution 80–92% of agent time | tool_seconds, result.json | 5 |
| Tools v3: Opus skills 8.9 → 4.2 min (33/40 faster, p 1.4e-5); no-output 4 → 0 | tools_v3.json | 6 |
| Tools v3: Opus skills − code +0.003 (Holm 0.028); Sonnet +0.024 (p 0.017, secondary) | tools_v3.json | 6 |
| Tools v3 primary not significant (+0.037, sign p 0.12) | tools_v3.json | 6 |

## Section plan (main ≈ 9 pages)
0. Abstract (≈180 words): problem → protocol → three findings with the key numbers (primary
   +0.104; Opus code 0.975 vs 0.951; tools v3 time halving and the non-significant primary).
1. Introduction (1.25 p): program is the product; mesh scores vs executed scores; three questions;
   contributions C1–C4; Figure 1 (hero, two panels: held-out arms with validity; agents vs pipeline).
2. Related work (0.6 p): mesh/point-cloud-to-CAD (DeepCAD, Point2Cyl, zone graphs, CAD-Recode,
   CADFit, CADBench data), agentic CAD (ReAct, Toolformer, SWE-agent; CAD-Assistant, CADReasoner,
   IterCAD, CADFather). Reuse existing verified bib entries only; positioning table.
3. Execution-based evaluation (1.0 p): replay + validity + judge + gating; cohorts and their
   disjointness; statistics; preregistration and amendment policy. Figure 2: input mesh → program
   that fails → execution-verified repair → detail map (development example, labelled).
4. Study 1 — the optimizer held out (1.75 p): arms d0→dx→v2→v3→trim; Table 1 (gated IoU by split,
   validity, mean/median minutes, contrasts with intervals and Holm p); recovery sensitivity
   sentence + appendix table; trim decomposition; runtime. Placeholders for section-only,
   rejudge, surface.
5. Study 2 — frontier agents on reserved parts (1.5 p): harness, toolsets (code includes
   inspection + execution feedback), settings; Figure 3 (simple_closed_models: score/min/cost);
   Table 2 (agents vs pipeline arms on the same 40); failure decomposition; tool-time share.
6. Study 3 — removing tool overhead (1.25 p): profiling → exact changes + check cap; protocol;
   Figure 4 (simple_tools_v3); Table 3 (primary + secondary with sign p / Holm); time results.
7. Discussion & limitations (0.6 p): what changes when you execute; where optimizer stages help;
   limits (list in narrative).
Reproducibility statement; Appendix: amendments and execution logs verbatim summary; recovery
sensitivity table; per-split tables; harness/tool specs; Claude settings; cost accounting
(retained vs discarded); profiling details and equivalence tests; dev history.

## Figures/tables
F1 hero (new, make): (a) held-out arms gated IoU with 95% CI + invalid counts; (b) agents vs
   pipeline on the reserved 40. Data: results/heldout/*.json, results/closed/closed_vs_pipeline.json.
F2 detail example: bench/figures/v2_2026-10-23/detail_00642725.png (development part).
F3 simple_closed_models.png. F4 simple_tools_v3.png.
T1 held-out pipeline; T2 agents vs pipeline (40); T3 tools-v3 comparisons; T-App recovery.

## Numbers macros
Rebuild paper/numbers.tex from the result files by a script (bench/paper_numbers.py) so every
number in the text is generated; pending values render as \pending{...} (visible red text).

## Citation policy
Only existing verified bib entries (references.bib); any new citation via DBLP/CrossRef or marked
[VERIFY]. Claude models named with version strings, no citation.

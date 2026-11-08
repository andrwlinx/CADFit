# Paper Claim Audit Report

**Date**: 2026-11-08  
**Auditor**: GPT-6-Astra ultra (fresh zero-context thread 01a1b8fa-e4f3-7d62-ab7d-4441af96f960)  
**Paper**: Execute the Program (round 0 draft)

## Overall Verdict: FAIL

All score numbers reproduce; FAIL for trim replay-limit disclosure, two missing brackets, delivery wording, figure hatching and missing equivalence evidence. Fixes applied after this audit; re-audit due in Phase 5.5.

## Issues and fixes

| # | Status | Issue | Fix applied |
|---|---|---|---|
| X01 | config_mismatch | trim records use the trim stage's 600 s replay, not the common 900 s | disclosed in Sec. 3 and 4; common re-judging pending |
| X02-03 | ambiguous_mapping | median column = mean of per-run medians | caption defines aggregation |
| X04-05 | number_mismatch | missing original brackets dx built-invalid 1[0], v2 seed2 2[1] | brackets added |
| X06 | scope_overclaim | delivery described as always execution-verified | fallback described; 22 + 48 unverified reported |
| X07 | ambiguous_mapping | abstract 'every delivered program valid' (479/480 in Study 3) | scoped to Opus |
| X08 | number_mismatch | model-time hatching used normalized share | uses recorded model seconds |
| X09 | ambiguous_mapping | tools field says v2 for all episodes | appendix explains version provenance by frozen-tree path |
| X10 | ambiguous_mapping | source-model disjointness vs two shared document hashes | wording changed to model index; disclosed |
| X11 | missing_evidence | equivalence tests not saved | bench/tools_equivalence.py -> results/tools/equivalence.json; macros |
| X12-13,X16,X18-19,X22 | unsupported_claim | interpretive overreach / caption color | softened or removed |
| X14-15,X17,X20 | missing_evidence | settings, logs, chronology not in result files | cited to code and protocol execution logs |

All score tables, intervals, deltas, costs and counts reproduced (status rounding_ok / exact_match). Full reviewer response: .aris/traces/paper-claim-audit/.
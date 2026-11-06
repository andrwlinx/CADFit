# Tools v3 study — protocol (drafted 2026-11-06, before any v3 episode or any fresh3 part exists)

## Question
Do faster agent tools (v3) change what closed-model agents deliver, and do the CADFit
skills add value over plain code once both get the same faster checking?

## What changed (v2 -> v3), and how it was developed
Developed and measured only on development parts (bench/cadbench/fresh, dev); no reserved
fresh2 part and no fresh3 part was used. Profile: bench/profile_tools.py ->
results/tools/profile_v2_local.json.

Exact changes (outputs identical to v2, verified on development inputs):
1. `fit_primitives.remove_duplicate_points_2d`: KD-tree neighbours instead of an all-pairs
   loop (300 randomized cases identical; ~200x faster on 3,500-point loops).
2. `analyze_revolve_axis.rotate_points_around_axis`: vectorized Rodrigues rotation
   (bit-identical on 200 randomized cases; fit_revolve 11.7 s -> 1.2 s on one dev part).
3. `fit_primitives.segment_greedy_fit`: the line error of a run from running sums in O(1);
   wherever that value is within 1e-6 (relative) of a threshold it is compared with, the
   former SVD fit decides (fitted output identical on all 162 sketches of 8 dev parts x 9 planes;
   fitting time 559 s -> 19 s with changes 1+3).
4. `score.robust_iou`: the normalized target and its manifold are loaded once per process
   (18/18 judge values identical).

Behavioural change (not output-identical):
5. Check cap: one executed check of a model change (replay + judge) gets at most
   CHECK_CAP = 120 s (v2: replay up to 180 s, judge unbounded; single tool calls reached
   ~1,770 s). A check that does not finish leaves the step in the model **unchecked**.
   **Delivery rule (frozen):** the delivered answer is the best *checked* valid program
   (higher validity, then higher in-episode IoU), as in v2; an unchecked program is never
   delivered unless no checked valid program exists, in which case the export falls back
   exactly as v2 does. Offline scoring evaluates that one delivered program only.
   The same cap and delivery rule apply to the code and skills toolsets.

## Cohort
`fresh3`: a new seeded draw with bench/fetch_cadbench.py — 20 benchA-hard + 20 benchE-hard
CADBench parts taken after every earlier set, excluding every file_id *source model*
already on disk in any set (test, dev, smoke, beamfix5, fresh, fresh2). Drawn and
downloaded after this protocol is committed; not inspected before the runs finish.

## Conditions (2 x 2, three independent episodes per part)
tools {v2 (frozen tree at the commit before these changes), v3 (frozen tree at the commit
that adds this protocol's code)} x toolset {code, skills}, for Claude Opus 5.5 (primary)
and Sonnet 5.5 (secondary). Same budget as before: 40 calls, 30 minutes, effort high,
CADFIT_AGENT_EXEC=1. Conditions interleaved per part on comparable nodes (mit_preemptable,
rocky8, node4002 excluded; sandboxed-replay preflight).

## Endpoints and analysis
Primary endpoint: validity-gated IoU of the delivered program, re-judged offline by
score.py's CAD replay (bench/agentsk_score.py), repeats averaged within part; a missing
delivery scores 0 and stays in the denominator.
- Primary comparison: Opus skills v3 - Opus skills v2 (does the tool package improve).
- Secondary: Opus skills v3 - Opus code v3 (skills vs code under equal checking);
  Opus code v3 - Opus code v2; the same three for Sonnet.
Paired bootstrap over parts, resampled within split, 95% intervals; Holm over the sign
tests of the three Opus comparisons. Also reported: mean/median minutes per part, tool
vs model time, API cost, deliveries, in-episode verification, unchecked steps, and
failure causes (no output, execution timeout, invalid geometry, judge failure).

## Stopping and cost
One run of every cell; no additional episodes after outcomes are seen. 960 episodes
(2 models x 2 tool versions x 2 toolsets x 40 parts x 3); expected API cost about $165
(chosen by the user 2026-11-06, beyond the remaining Ultra credit). Launch is stopped if
the study's spend passes $200.

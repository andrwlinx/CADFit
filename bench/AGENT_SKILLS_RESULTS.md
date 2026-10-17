# Open models as CAD agents with CADFit skills

20 fresh-cohort parts (ledger A-005); budget 40 tool calls / 30 min per episode (A-006); episode answer = best model seen by agent-visible IoU (A-007). IoU = corrected judge on the mesh; IoU(CAD) = judge on the solid rebuilt by running the final CadQuery program (A-008, headline). Failed or missing episodes score 0.

## Results

| condition | IoU | IoU(CAD) | CAD invalid (of models) | episodes with a model | tool calls / episode | GT trial evals / episode | stops |
|---|---|---|---|---|---|---|---|
| devstral2-24b/code | 0.3049 | 0.3048 | 1 | 20/20 | 40.0 (n=20) | 0 | budget 20 |
| devstral2-24b/skills | 0.7758 | 0.7760 | 1 | 20/20 | 37.2 (n=20) | 0 | budget 16, finish 4 |
| gemma4-31b/code | 0.5928 | 0.5929 | 1 | 20/20 | 22.9 (n=20) | 0 | time 14, finish 4, budget 2 |
| gemma4-31b/skills | 0.8920 | 0.8920 | 0 | 20/20 | 27.9 (n=20) | 0 | finish 8, budget 6, time 6 |
| gptoss-120b/code | 0.5515 | 0.5565 | 0 | 20/20 | 40.0 (n=20) | 0 | budget 20 |
| gptoss-120b/skills | 0.8124 | 0.8123 | 1 | 20/20 | 38.2 (n=20) | 0 | budget 18, no tool call 2 |
| gptoss-20b/code | 0.4218 | 0.4218 | 0 | 18/20 | 25.5 (n=20) | 0 | finish 10, no tool call 6, budget 3, api error 1 |
| gptoss-20b/skills | 0.7322 | 0.7324 | 0 | 18/20 | 25.1 (n=20) | 0 | finish 10, no tool call 4, budget 4, api error 2 |
| no-llm-policy/skills | 0.8095 | 0.8095 | 0 | 19/20 | 22.4 (n=20) | 69 | done 18, budget 2 |
| qwen36-35b-a3b/code | 0.4648 | 0.4648 | 0 | 18/20 | 39.5 (n=20) | 0 | budget 19, no tool call 1 |
| qwen36-35b-a3b/skills | 0.8525 | 0.8537 | 0 | 20/20 | 37.2 (n=20) | 0 | budget 16, finish 4 |
| qwen38-27b/code | 0.3070 | 0.3069 | 0 | 9/20 | 14.2 (n=20) | 0 | no tool call 16, time 3, finish 1 |
| qwen38-27b/skills | 0.7302 | 0.7299 | 0 | 16/20 | 22.2 (n=20) | 0 | time 10, no tool call 8, finish 1, budget 1 |
| pipeline/beamkh | 0.9124 | 0.8597 | 3 | 20/20 | nan (n=0) | 0 | — |
| pipeline/beamsec | 0.9536 | 0.9036 | 1 | 20/20 | nan (n=0) | 0 | — |
| pipeline/best_of_beam_section | 0.9494 | 0.8964 | n/a | n/a | nan (n=0) | 0 | — |

## Skills vs code-only, paired over parts (IoU(CAD))

| model | skills | code | skills − code [95% CI] | skills better / worse (±0.01) |
|---|---|---|---|---|
| devstral2-24b | 0.7760 | 0.3048 | +0.4713 [+0.3575, +0.5785] | 18 / 1 |
| gemma4-31b | 0.8920 | 0.5929 | +0.2991 [+0.1726, +0.4339] | 16 / 1 |
| gptoss-120b | 0.8123 | 0.5565 | +0.2558 [+0.1440, +0.3740] | 16 / 1 |
| gptoss-20b | 0.7324 | 0.4218 | +0.3106 [+0.1571, +0.4601] | 15 / 3 |
| qwen36-35b-a3b | 0.8537 | 0.4648 | +0.3889 [+0.2556, +0.5195] | 17 / 3 |
| qwen38-27b | 0.7299 | 0.3069 | +0.4230 [+0.2386, +0.6085] | 14 / 3 |

## Against the deterministic pipeline (IoU(CAD), paired)

| condition | vs pipeline/beamsec [95% CI] | vs best-of beam+section [95% CI] |
|---|---|---|
| devstral2-24b/code | -0.5989 [-0.6952, -0.4868] | -0.5916 [-0.7075, -0.4396] |
| devstral2-24b/skills | -0.1276 [-0.2254, -0.0343] | -0.1203 [-0.2223, -0.0160] |
| gemma4-31b/code | -0.3107 [-0.4509, -0.1757] | -0.3035 [-0.4636, -0.1333] |
| gemma4-31b/skills | -0.0116 [-0.0411, +0.0268] | -0.0043 [-0.0971, +0.1032] |
| gptoss-120b/code | -0.3471 [-0.4787, -0.2133] | -0.3399 [-0.4895, -0.1735] |
| gptoss-120b/skills | -0.0913 [-0.1835, -0.0149] | -0.0841 [-0.2068, +0.0465] |
| gptoss-20b/code | -0.4819 [-0.6233, -0.3331] | -0.4746 [-0.6271, -0.3022] |
| gptoss-20b/skills | -0.1713 [-0.2960, -0.0701] | -0.1640 [-0.3244, -0.0043] |
| no-llm-policy/skills | -0.0941 [-0.2035, -0.0041] | -0.0868 [-0.2170, +0.0408] |
| qwen36-35b-a3b/code | -0.4389 [-0.5923, -0.2774] | -0.4316 [-0.5939, -0.2558] |
| qwen36-35b-a3b/skills | -0.0499 [-0.1043, +0.0065] | -0.0427 [-0.1325, +0.0568] |
| qwen38-27b/code | -0.5967 [-0.7738, -0.4069] | -0.5895 [-0.7695, -0.3914] |
| qwen38-27b/skills | -0.1737 [-0.3131, -0.0557] | -0.1665 [-0.3086, -0.0485] |

## How the models used the skills (skills toolset)

Per episode with a transcript (n shown), same denominator as the table above.

| model | n | calls/episode | detect_directions | extract_sketch | fit_extrude | fit_revolve | section_extrude | add_code | add_candidate | tool errors |
|---|---|---|---|---|---|---|---|---|---|---|
| devstral2-24b | 20 | 37.2 | 0.9 | 3.8 | 6.8 | 0.3 | 1.2 | 3.4 | 7.2 | 12/745 |
| gemma4-31b | 20 | 27.9 | 0.4 | 3.1 | 2.7 | 0.1 | 1.1 | 3.5 | 2.9 | 17/559 |
| gptoss-120b | 20 | 38.2 | 1.0 | 4.8 | 3.6 | 0.1 | 1.6 | 3.6 | 4.0 | 22/764 |
| gptoss-20b | 20 | 25.1 | 0.9 | 2.1 | 1.8 | 0.1 | 1.6 | 2.2 | 2.6 | 44/503 |
| qwen36-35b-a3b | 20 | 37.2 | 1.0 | 4.9 | 2.2 | 0.0 | 1.6 | 3.4 | 2.5 | 47/744 |
| qwen38-27b | 20 | 22.2 | 1.0 | 1.8 | 1.6 | 0.0 | 0.3 | 3.1 | 1.3 | 27/445 |

## Post-hoc sensitivity: qwen38-27b with a 32k per-turn token cap (A-038)

Not part of the declared study; the 16k rows above are the result.

| toolset | IoU(CAD) 16k | IoU(CAD) 32k | 32k − 16k [95% CI] | stops (32k) |
|---|---|---|---|---|
| skills | 0.7299 | 0.7830 | +0.0531 [-0.1185, +0.2224] | time 16, finish 4 |
| code | 0.3069 | 0.5407 | +0.2338 [-0.0149, +0.4749] | time 19, budget 1 |

## Caveats

- One episode per (model, toolset, part); no repeat variance (deferred). Confidence intervals: paired percentile bootstrap over parts (10,000 resamples, seed 0) — part sampling only (A-028). "Better/worse" counts need |Δ IoU(CAD)| > 0.01 (A-029).
- The no-LLM policy also scores every candidate union/cut against the GT without spending tool calls ("GT trial evals" column, A-026): a ceiling-style control with more oracle access than an agent.
- Answer selection uses ground-truth IoU (A-007), as does every condition and the best-of control.
- The agent fit_revolve carries a revolve-split bug fix the frozen pipeline arms do not (A-016).
- Pipeline references are the frozen fresh-cohort runs (bench/runs/fresh_scores.json), not rerun.

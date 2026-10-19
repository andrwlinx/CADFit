# Reviewer Memory

Reviewer: Codex gpt-6-astra (ultra), thread `01a13934-b637-7593-9656-6b4e23834789`.
Rounds 1–2 ran as `/aris:research-review`. This auto-review-loop (run_20261014_49c46147)
continues the same thread.

## Round 1 — Score: not given (verdict: reject / not ready)

### Raw Reviewer Response (verbatim)

**I would reject the current work as a NeurIPS/ICML submission.** There are useful engineering improvements here, but I found current scoring defects, invalid CAD outputs behind "valid" scores, and a simple deterministic control that outperforms the reported agent results.

I read the complete results log and earlier reports, checked implementation and frozen run snapshots, recalculated saved-score summaries, and ran geometry probes without changing files. The agent and ABC60 score JSONs exist locally, but their reconstruction files and trajectories do not; those results could be checked arithmetically, not fully replayed.

1. **The independent judge demonstrably fills internal cavities.**

   [score.py:99](/Users/Andrewlin/CADFit/bench/score.py:99) calls [iou.py's multi-body conversion](/Users/Andrewlin/CADFit/iou.py:225), which splits surface components and unions all of them—including negative-volume cavity shells.

   I reproduced this on actual saved outputs:

   | Reconstruction | Current judge | Cavity-preserving exact IoU |
   |---|---:|---:|
   | Latest beam, `00344388` | 0.975826 | 0.986239 |
   | Rules, `00014841` | 0.910187 | 0.947503 |

   For `00344388`, the conversion increases reconstructed volume from 0.261255 to 0.264049. Winding-number checks confirm that genuinely empty cavities become filled. The existing volume-consistency checks still pass.

   This is a current defect, distinct from the cavity bug already fixed in `gwn_repair.py`. The pipeline and judge share the faulty helper, so their agreement is not independent validation.

   **Scoped fix:** preserve cavity shells while resolving overlapping solids, then rescore existing outputs. These examples underestimate improved arms; they do **not** establish that the overall improvement disappears.

2. **A good scored mesh does not establish a valid executable CAD reconstruction.**

   With exact-union enabled, [run_pipeline.py:1111](/Users/Andrewlin/CADFit/run_pipeline.py:1111) can produce the scored mesh through manifold booleans without executing the combined CadQuery program. The scorer then assigns [“valid”: true](/Users/Andrewlin/CADFit/bench/score.py:155) without checking that program's CAD geometry.

   I executed saved programs in memory using the repository's CadQuery environment:

   - [`00706786`](/Users/Andrewlin/CADFit/bench/runs/p3test2_beam/00706786_3dac85c0e64e90c849e110f3_step_000/best_greedy_parallel_iterative.py:119) scores **0.979944**, marked valid, but its resulting CAD shape fails `isValid()`; one of four constituent solids is invalid.
   - `00409618` scores **0.928521**, marked valid, but two of its 33 constituent solids are invalid.

   Thus the current results measure saved-mesh reconstruction quality, with insufficient evidence for executable-CAD validity. Agent export also writes its CAD program separately from the scored manifold mesh.

   **Scoped fix:** execute final programs, check their resulting solids, and judge their regenerated geometry. Report mesh fidelity and CAD validity separately.

3. **The missing simple baseline substantially undermines the agent story.**

   I ran this deterministic diagnostic on all ten agent cases:

   - Take target sections through the normalized bounding-box midpoint along x, y, and z.
   - Apply the existing [section tool's simplification and rounding](/Users/Andrewlin/CADFit/agent/cad_tools.py:318).
   - Extrude each section through the target's extent along that axis.
   - Retain the best proposal or pipeline model using the agent's internal evaluator.

   | Method, same ten parts | Mean judge IoU |
   |---|---:|
   | Pipeline | 0.6264 |
   | Agent, average over three refine runs | 0.6998 |
   | Agent, best result per part across three runs | 0.7363 |
   | Deterministic section-extrusion diagnostic | **0.7483** |

   All seven selected new extrusion proposals were subsequently built in **actual CadQuery**, passed shape validity checks, and were independently judged after tessellation and an STL roundtrip. Selection plus CAD replay took approximately 35 seconds on this Mac, excluding the shared pipeline preparation.

   Two particularly revealing cases:

   - `00182325`: agent **0.9199**; simple section extrusion **0.9957**. Even rescaling the existing reconstruction to the target bounds reaches **0.9781**.
   - `00875997`: simple section extrusion gives **0.9252938202**, exactly the reported repeatable agent score.

   Those two repeatable agent wins account for **74.5% of its average improvement**.

   This control was devised after inspecting the results, so it is **a post-hoc diagnostic, not a new held-out benchmark**. Nevertheless, the current evidence does not establish an advantage from LLM planning. It establishes missing geometric proposals that a very cheap controller can supply.

4. **The CADBench headline is mislabeled and does not isolate beam search.**

   The **0.8445 baseline is not upstream stock CADFit**. Its [frozen implementation](/Users/Andrewlin/CADFit/bench/runs/p3test_base_code/run_pipeline.py:1344) already enables correctness fixes, caching, guarded refinement, and other changes. The runner has a separate [stock configuration](/Users/Andrewlin/CADFit/bench/run_full_arms.sh:20) that disables them.

   Furthermore, baseline/rules and latest beam use different code snapshots. Two baseline failures, `00694965` and `00714375`, occur before composition search: they produce no valid evaluated candidates. Their rescue contributes:

   - **32.4%** of the baseline-to-beam improvement.
   - **63.8%** of the rules-to-beam improvement.

   Failure recovery is valuable and belongs in the main result. It cannot be attributed to beam composition search when the original failure precedes that search.

   **There is legitimate isolated beam evidence:** the same-code development comparison gives **0.854276 → 0.858940**, a gain of **0.004664**, with a paired bootstrap interval approximately **[0.00127, 0.00858]**. Those figures remain conditional on correcting the judge. This is a much smaller algorithmic effect than the headline suggests.

5. **The agent's budget and non-regression claims are too strong.**

   The deadline is checked [before an API request](/Users/Andrewlin/CADFit/agent/agent_loop.py:195), but returned tool calls execute without another deadline check. Requests themselves can take 900 seconds and retry.

   **26 of 30 refine trials exceed 20 minutes; the maximum is 25.06 minutes.** Without the trajectories, I cannot determine which improvements existed before the nominal deadline. Report these as soft-deadline runs or enforce the stated budget.

   Best retention itself is correctly implemented for the **internal objective**. It does not guarantee non-regression under a different judge.

   Also, `00479221`'s repeated **0.780793 → 0.786297** "win" requires no LLM: loading and re-exporting the pipeline manifold changes the judge from Monte Carlo to exact evaluation. I reproduced it. Include a no-op initialization/export control and exclude this from substantive agent win counts.

6. **The ABC evaluation has a real domain error and inadequate precision on some parts.**

   The soup scorer samples only `[-1.05,1.05]³`; material outside that cube is merely flagged, not included in the denominator. This occurs in the latest reported artifact: [baseline `00000156`](/Users/Andrewlin/CADFit/bench/runs/abc60c_ws/abc60cr_pscores.json:3) has `recon_exceeds_box: true`.

   Its score is therefore a clipped-domain estimate. Rescore over bounds covering both shapes. Any omitted exterior volume favors the baseline, so this particular correction would not explain away the repair gain.

   Separately, nominally using 100,000 points does not ensure precise thin-part scores. For ABC40 `00001081`, the reported repair scores come from:

   - Base: **67/94** intersection/union samples, IoU 0.7128.
   - Beam: **87/119**, IoU 0.7311.

   Their approximate Monte Carlo standard errors are **0.047 and 0.041**. A 0.01 win/loss threshold is not meaningful at that precision. Use tighter covering bounds or more effective occupied samples and check convergence.

   Finally, [the judge imports the repair's winding-number implementation](/Users/Andrewlin/CADFit/bench/score.py:27). Agreement with its 0.5 occupancy convention is a legitimate result; recovery of the soup's **"true volume"** is unproven. Controlled corruption of clean CAD would provide an independently known target.

7. **The evaluation history cannot support untouched-test or broad model-comparison claims.**

   Exact-ID split disjointness and seeded selection check out. However, [REPORT3 explicitly analyzes development and test geometry](/Users/Andrewlin/CADFit/bench/REPORT3.md:51) and uses that analysis to reorder priorities. The weakest test cases then support agent-loop adjustments. ABC60 was also reused during fixes.

   Additional qualifications:

   - Latest CADBench scores comprise **77 exact and 23 Monte Carlo** evaluations.
   - Sixteen of its 100 target STLs are non-watertight; the judge may alpha-wrap these and still label the subsequent calculation "exact."
   - REPORT3's development confidence intervals belong to an older evaluator.
   - **0.700 ± 0.021** is correctly calculated, but the ± is the sample standard deviation of **three run means**, not uncertainty across unseen shapes.
   - Model comparisons change sampling, context handling, and output-token budgets. They compare configurations, not isolated model capability.

**What can honestly be claimed today**

| Workstream | Defensible claim |
|---|---|
| Search engineering | Several engineering changes improve saved-mesh quality and reliability on these development benchmarks. Same-code evidence supports a modest beam-search benefit. |
| GWN repair | The merged ABC60 scores improve from **0.663076 to 0.725041** under the current evaluator. This supports better agreement with GWN-defined occupancy on a reused development set, pending measurement corrections. |
| Agent | This configuration improves selected pipeline failures. Its superiority over inexpensive deterministic geometry corrections is currently unsupported. |

The headline arithmetic checks out. ABC60's merge contains all 60 intended parts and matches its source score files. Agent failures remain in the denominator. The current repair correctly skips watertight inputs and preserves cavities during speck removal. These are correct aspects of the work.

**The strongest current paper story is a careful CAD reconstruction engineering and evaluation study.** A focused workshop/tooling paper is plausible after fixing measurement and executable-output validity. The agent story needs to survive the simple control above before it deserves more expensive experimentation.

For NeurIPS/ICML, novelty is also a serious obstacle. Generalized winding-number reconstruction is established geometry processing. More directly, [CADFather, submitted October 6, 2026](https://arxiv.org/html/2610.09127v1), already describes mesh-to-CAD tool orchestration, geometric feedback, alternative candidates, and best-result retention, with broad evaluation. "An LLM uses CAD tools and keeps its best reconstruction" is insufficient differentiation. [Generalized winding-number prior work](https://users.cs.utah.edu/~ladislav/jacobson13robust/jacobson13robust.pdf) likewise needs clear acknowledgment.

The narrative currently mixes correctness fixes, search changes, repair, and model comparisons without isolating a central scientific claim. Lead with a measured mechanism. Avoid "free gain," guaranteed external-score monotonicity, untouched-test language, and reasoning claims based on examples reproduced by direct extrusion.

**The minimum experiment package should be staged:**

1. **Repair measurement and replay existing artifacts first.** Fix cavity handling and soup bounds; check Monte Carlo convergence on the demonstrated thin cases; validate final CAD programs; regenerate tables under one evaluator. Retrieve the missing workstation outputs and trajectories.

2. **For the engineering paper, run corrected baseline, rules, and beam from one implementation on 40–60 fresh parts.** Hold preprocessing and seeds constant. Report failures, paired quality differences, runtime, CAD validity, and program size. At five concurrent parts, a 60-part, three-arm matrix is roughly **9–12 hours** under the stated timings, before overhead.

3. **For the agent, first freeze and benchmark the deterministic section-extrusion control.** If an agent advantage remains on fresh cases, compare it against that control and equal-extra-time search. Forty fresh parts with two agent repetitions cost about **27 GPU-hours** at a genuinely enforced 20-minute budget. Add candidate-only and reduced-feedback ablations on a prespecified subset; further model-size sweeps are lower priority.

4. **Keep GWN validation separate unless it is the main claim.** Use clean CAD with controlled missing faces and fresh raw soups; measure against the original closed geometry where available, including cold repair time.

With 16 GB free disk, batch these runs and retain final programs, meshes, scores, and trajectories. The existing runner's default 80 GB free-space threshold also needs appropriate configuration.

**The present work is not submission-ready. The next decisive step is corrected measurement plus simple controls—not a larger agent benchmark.**

### Memory Update
- **Suspicion**: judge/pipeline share iou helpers; agent gains are geometric proposals; CADBench gain is mostly failure rescue.
- **Unresolved**: all seven findings; no fresh cohort; no equal-time control.

---

## Round 2 — Score: not given (agreed plan)

### Raw Reviewer Response (verbatim)

**The revised direction is sensible, but the plan needs stronger controls before it fixes the earlier weaknesses.** The accepted defects are still present in the current code; this is a proposed repair package, not verified fixes.

I agree with clarification **(a)**, with narrower wording: **the pipeline lacks reliable full-span extrusion proposals for some section contours.** It already generates single extrusions and has a [best-single fallback](/Users/Andrewlin/CADFit/greedy_search.py:1136); `00182325` demonstrates incorrect extrusion parameters. Planar, axis-aligned surfaces motivate this prior but do not imply that whole objects are prisms.

Residual-hard evaluation is legitimate. It answers a conditional question about failures of the strengthened pipeline; it cannot establish general agent superiority.

| Stage/result | Claim it can support | What remains necessary |
|---|---|---|
| Corrected judge and executed final programs | Reported fidelity corresponds to valid, replayable CAD outputs | Preserve cavities; fix sampling bounds/precision; specify target-solid construction for non-watertight targets |
| Same-code base → rules | Benefit of the **whole rules/objective/subsampling package** | Cannot attribute this difference to individual ingredients |
| Same-code rules → beam | Incremental benefit of beam search | Identical preprocessing, candidate generation, budgets, and scoring |
| Pipeline + section proposals | Benefit of this proposal family on fresh parts | Compare integrated search against the cheap standalone control |
| Agent on residual-hard parts | Conditional improvement beyond strengthened geometry methods | Prespecified eligibility, equal-extra-time search control, repeated runs, and eligible fraction |

**The important unresolved integration issue:** adding candidates can change the search path. It need not reproduce the standalone control's result. Keep these quantities distinct:

- Original pipeline output.
- Best of the three section extrusions.
- Best of original pipeline and those extrusions.
- Pipeline with the extrusions inserted into its candidate pool.

The middle two are nearly free to measure. Preserve the original reconstruction as an alternative when testing integration; the existing best-single fallback does not protect its potentially better multi-operation model.

**Minimum package, in order:**

1. **Finish measurement and output correctness on existing development artifacts.** Reproduce the known cavity and invalid-CAD cases, correct them, execute final programs, and regenerate scores. Freeze the section recipe and agent eligibility rule on existing development data. Keep GWN claims limited to its occupancy convention unless you add independent clean-solid validation.

2. **Freeze one fresh cohort and all configurations before evaluating it.** Use **60 previously uninspected parts: 30 benchA-hard and 30 benchE-hard**. Explicitly exclude previously inspected IDs and use a separate empty input directory. A new downloader seed alone is insufficient: [its selection excludes only that invocation's IDs](/Users/Andrewlin/CADFit/bench/fetch_cadbench.py:71), while runners process every STL in the directory.

3. **Run four system arms**, all from one code version, with `--seed 0 --max-iterations 1`:

   | Arm | Configuration |
   |---|---|
   | A | Corrected `base` defaults |
   | B | `--persistent-cq --exact-union --cut-phase --event-slices --detect-directions --translation-max-points 400` |
   | C | B plus `--beam 4` |
   | D | C with the fixed three section-extrusion proposals added |

   Also report the standalone best-of-C-and-sections control. No full factorial is needed unless you want claims about individual rules.

   Use approximately **five concurrent parts**, with `CADFIT_INNER_WORKERS=15`. These 240 runs cost roughly **12–16 hours**, excluding scoring, CAD replay, and long tails. Report paired confidence intervals, invalid/failure counts, runtime, and program size.

4. **Make the agent study optional and conditional.** Choose a cutoff on development data—for example, strengthened-pipeline IoU below **0.90**—then apply it unchanged to the fresh cohort. Report how many qualify. If necessary, randomly select at most 20 eligible parts before any agent outcomes; do not change the cutoff to obtain favorable cases.

   Compare the same starting artifacts under:

   - Strengthened pipeline, no further computation.
   - Same candidate pool with up to **1,200 seconds of additional geometric search**.
   - Qwen3.8-27B-INT4, refine only, **40 calls / enforced 1,200 seconds**, two repetitions, using the existing sampling configuration.

   Twenty parts × two repetitions costs **13.3 GPU-hours**. Report average repetitions rather than best-of-two. Report conditional improvement and the estimated overall benefit of invoking the agent only when the gate fires. Equal wall time still requires separate CPU/GPU cost reporting.

   Do not use the existing `ms` arm unchanged: it also enables loft/sweep, confounding the comparison.

**Disk needs one concrete adjustment.** The current runner requires 80 GB free and deletes agent candidate history. Configure its existing disk limits after a small pilot and retain the files the agent actually consumes. The current ten-part preparation occupies about **9.45 GiB**, but its candidate files, metadata, and final outputs total roughly **116 MB**. Preserve final CAD, meshes, scores, configurations, logs, and agent trajectories before removing bulky intermediates.

**I would write the engineering/evaluation story:** "Correct measurement and simple geometric proposals explain apparent gains from CAD agents." Keep that conclusion conditional on the fresh results.

I agree with **(b)**: drop the agent as a headline contribution. [CADFather](https://arxiv.org/abs/2610.09127) already covers broad tool orchestration and best-result retention. A differentiated agent claim would require fresh evidence that feedback-guided edits outperform the strengthened geometric controls at comparable cost.

The realistic initial target is a **CAD/geometry or ML-for-design workshop**. This package could support a credible workshop paper; it does not, by itself, resolve the novelty gap for NeurIPS/ICML main track.

### Memory Update
- **Previous suspicions addressed?**: no (plan only).
- **Unresolved**: everything in round 1 until fixes are run; integration vs standalone control distinction; fixed gate.

---

---

# run_20261018_3f681321 (fresh loop; prior run_20261014_49c46147 was stale)

## Round 1 — Score: 4/10 (thread 01a151f6-8b58-76b3-98d6-c0f67e4a1e69)

### Raw Reviewer Response (verbatim)

**Not ready for submission. I would score this 4/10 at a top venue.** The execution audit is useful, and the skills-versus-code improvements are substantial. But the system still optimizes a different artifact from the program it delivers, contains reproducible geometry defects, and lacks completed controls establishing what the agent contributes.

I reviewed the code, raw scores, available generated programs, and compiled paper. One important limitation: this checkout contains `fresh_scores.json`, `fresh_scores.log`, and `fresh_section_control.json`, but **none of the fresh per-part programs, pipeline logs, or replay records**. Agent transcripts are also absent. Consequently, the exact operation responsible for each historical fresh failure cannot be established here. Exception strings are evidence of failure, not sufficient evidence of its geometric cause.

**What the raw results establish**

These means are recomputed from [fresh_scores.json](/Users/Andrewlin/CADFit/bench/runs/fresh_scores.json). “Valid CAD IoU” assigns zero to missing, unbuilt, or OCC-invalid outputs.

| Arm | Mesh IoU | Executed CAD IoU | Valid CAD IoU | Missing reconstruction | Replay failed | Built but invalid |
|---|---:|---:|---:|---:|---:|---:|
| A | 0.8204 | 0.8215 | 0.8215 | 2 | 0 | 0 |
| B | 0.8767 | 0.8303 | 0.7993 | 1 | 3 | 2 |
| C | 0.8799 | 0.7994 | 0.7528 | 1 | 5 | 3 |
| D | 0.9376 | 0.8886 | 0.8563 | 1 | 2 | 2 |

Thus, C’s “six unbuilt programs” comprises **five failed replays and one missing reconstruction**. D’s validity-gated improvement over A is only **0.0348**, substantially below its mesh improvement of 0.1172.

The complete failure inventory, using part-ID prefixes, is:

| Part | Recorded outcome |
|---|---|
| `00154184` | A: no reconstruction |
| `00247424` | All arms: no reconstruction |
| `00232213` | B: replay crash recorded as `IndexError`; C: built invalid; D: 900-second timeout |
| `00365747` | B: 900-second timeout; C: `Standard_OutOfRange`; D: built invalid |
| `00528181` | B: built invalid |
| `00589302` | C: built invalid |
| `00642725` | B/C: `Null TopoDS_Shape`; D: `Standard_OutOfRange` |
| `00771160` | C/D: built invalid |
| `00883892` | C: `Null TopoDS_Shape` |
| `00892314` | B: built invalid; C: replay crash recorded as `IndexError` |
| `00983172` | C: `Null TopoDS_Shape` |
| `00090768` | D: **valid**, mesh 0.999268 versus CAD 0.001651 |
| `00966049` | Valid, but B/C: approximately 0.945→0.818; D: 0.950→0.821 |

The `00090768` failure alone contributes **0.0166** to D’s mean mesh–CAD gap—about one-third of that gap. It deserves diagnosis before any wider search experiment.

**Critical weaknesses, ranked**

**1. Executability and geometric fidelity are outside the pipeline’s acceptance criterion.**

This is the principal system defect. [cadquery_ops.py:2134](/Users/Andrewlin/CADFit/cadquery_ops.py:2134) returns a score from cached mesh booleans without executing the composition. The program is subsequently generated at [cadquery_ops.py:2858](/Users/Andrewlin/CADFit/cadquery_ops.py:2858). Refinement repeats the separation: successful mesh combination short-circuits program execution at [run_pipeline.py:1120](/Users/Andrewlin/CADFit/run_pipeline.py:1120) and [run_pipeline.py:1186](/Users/Andrewlin/CADFit/run_pipeline.py:1186).

That explains **why failed or geometrically wrong programs can win**, although it does not identify the precise OCC operation behind each missing historical replay.

Minimum fix: retain fast mesh scoring for proposal screening, but execute and score every proposed incumbent before accepting it. Maintain the best **executed, valid** program, including a simple single-candidate fallback. Export its tessellation as the delivered mesh. Validate both geometry and OCC status; `00090768` proves validity alone is insufficient.

For the listed failures, recover the saved programs and replay them operation by operation, retaining the first exception, invalid shape, or large geometry divergence. Do not infer “bad boolean” from `Null TopoDS_Shape` alone.

**2. Preprocessing corrupts an actual thin part and undermines D’s strongest proposal family.**

On `00729452`, the recorded D CAD IoU is **0.28055**, while the standalone section control reaches **0.98161**.

I reproduced the current decimation procedure in memory on this part:

- Original normalized thickness: **0.00181818**.
- Decimated thickness: **0.00623752**, approximately **3.43× larger**.
- The decimated mesh fails `is_volume`.

The responsible path is [run_pipeline.py:928](/Users/Andrewlin/CADFit/run_pipeline.py:928), followed by replacement of the downstream input at [run_pipeline.py:1007](/Users/Andrewlin/CADFit/run_pipeline.py:1007). Section proposals consume that changed input at [run_pipeline.py:845](/Users/Andrewlin/CADFit/run_pipeline.py:845); the standalone control consumes the original mesh at [bench/section_control.py:41](/Users/Andrewlin/CADFit/bench/section_control.py:41).

This is a reproduced preprocessing defect and a concrete explanation to test for the historical D/control discrepancy; the absent fresh logs prevent confirming its exact historical sequence.

Minimum fix: generate whole-part section proposals from the original normalized mesh and use that same reference for authoritative candidate scoring. Confine decimation to stages where its approximation is intended. This is higher leverage than widening the beam.

**3. Revolve coordinates are wrong away from the sketch origin; other geometry fixes remain split between implementations.**

[greedy_search.py:377](/Users/Andrewlin/CADFit/greedy_search.py:377) computes:

```python
mp_local = inverse_matrix @ mp_for_axis
```

For a world-space axis point, it must subtract the sketch origin before transforming. CadQuery subsequently transforms the supplied local coordinates back through the workplane.

This occurs in retained artifacts, not just a hypothetical translated example. In [the generated candidate for `00958981`](/Users/Andrewlin/CADFit/bench/runs/agentprep_beam/00958981_4824d49259c584bb126f3d91_step_000/sketch_10_revolve_1.py:5), the sketch origin is at z≈0.1334, but the axis also contains that displacement in its local z coordinate. Before rounding, the reconstructed world axis is at z≈0.2669 instead of z≈0.1334. The saved program executes and is OCC-valid. The emitter additionally perturbs both axis endpoints by `1e-3` at [cadquery_ops.py:460](/Users/Andrewlin/CADFit/cadquery_ops.py:460).

Separately, I directly confirmed that `00140273` has **67 loops at x=0**, all with areas between approximately 0.000216 and 0.000240. The pipeline discards every one at [split_loops.py:302](/Users/Andrewlin/CADFit/split_loops.py:302). The skills implementation retains them. Even-odd nesting and revolve split densification also differ between pipeline and skills.

Minimum fix: correct the axis transform, validate the emitted axis against the requested axis, and share the existing nesting, small-profile, and split-densification corrections across pipeline and tools. Add translated and rotated versions of the existing shaft regression; the current revolve test uses an origin-centered plane and misses this error.

**4. Tools provide execution feedback for individual pieces, but not for the assembled program.**

It would be incorrect to say the tools never execute CAD: they do. However:

- [agent/skills.py:136](/Users/Andrewlin/CADFit/agent/skills.py:136) executes individual candidates, then scores converted meshes.
- [agent/cad_tools.py:165](/Users/Andrewlin/CADFit/agent/cad_tools.py:165) assembles and evaluates manifold geometry.
- [agent/cad_tools.py:180](/Users/Andrewlin/CADFit/agent/cad_tools.py:180) selects the best history entry by that mesh score.
- [agent/cad_tools.py:372](/Users/Andrewlin/CADFit/agent/cad_tools.py:372) later emits different OCC union/cut operations.

The consequence appears in the results: invalid outputs reduce gpt-oss-120b skills from **0.8123 to 0.7687**, and Devstral skills from **0.7760 to 0.7365**.

Failures also lose useful information: `_register` returns `None`, which fitting tools can describe as “no extent matches” or “no symmetry axis,” conflating geometric mismatch with execution failure.

Minimum fix: make model-changing tools return executed-program IoU, build/validity status, and the failing operation when applicable. Compute missing/extra regions from the executed result. Preserve the previous valid incumbent on failure. Return distinct reasons for no proposal, failed build, invalid solid, and poor fit.

For revolve usability, provide candidate axis/plane suggestions and meaningful failure feedback. Do not force more revolve calls merely to improve a usage statistic.

**5. Harness behavior and budget accounting confound model comparisons.**

At [agent/agent_loop.py:339](/Users/Andrewlin/CADFit/agent/agent_loop.py:339), `nudges` is initialized once and incremented on no-tool responses, but never reset after successful tool use. The claimed “consecutive” behavior is therefore not implemented.

The time limit is checked between tools, without passing the remaining deadline into tool execution. Actual records exceed 30 minutes: `00354176` takes **2049.5 seconds** for Gemma/code and **2081.3 seconds** for the scripted policy.

The proposed matched policy also uses a different interaction economy: [agent/scripted_skills_policy.py:97](/Users/Andrewlin/CADFit/agent/scripted_skills_policy.py:97) charges a trial and then charges an accepted addition; agents add once and pay again only if they undo.

Minimum fix: reset consecutive-failure state, enforce remaining time inside expensive calls, and run the deterministic policy through the same model-changing interface. Report wall time and geometry evaluations alongside tool calls. Tune reasoning/token settings on already-used parts, then freeze them before comparing old and improved tools.

**6. The central controls and submission evidence are incomplete.**

The compiled paper contains `PENDING` results for the matched policy, Gemma repeats, and section-only tool ablation. It also describes those repeats and figure elements as though completed. The corresponding raw score files are absent. :codex-file-citation{path="/Users/Andrewlin/CADFit/paper/main.pdf" purpose="source"}

The existing unrestricted policy’s extra evaluations are disclosed correctly. Nevertheless, “no significant agent advantage” does not establish equivalence or prove that tools explain all gains. The missing section-only ablation is especially consequential given the strength of section proposals.

Minimum fix: complete the controls using the corrected shared tool implementation, retain their programs and transcripts, and rewrite conclusions from the resulting evidence. For top-venue positioning, execution-aware selection itself is already present in concurrent work: CADFather executes proposals and preserves the best valid program. The contribution must therefore be the demonstrated diagnosis, repair, and controlled tool-versus-policy result—not merely advocating execution. [CADFather paper](https://arxiv.org/abs/2610.09127)

**Highest-leverage experiments for targets (1)–(3)**

| Change | Comparison | Evidence of success |
|---|---|---|
| Execute and validate incumbent programs; retain valid fallbacks | Frozen D versus D with this change only | Higher valid CAD IoU; fewer missing/unbuilt/invalid outputs; lower absolute mesh–CAD discrepancy, including its upper tail |
| Original-mesh section proposals plus shared geometry corrections | Previous row versus corrected proposal generation | Further CAD-IoU gain; recovery of `00729452` and small-profile cases; translated revolve regressions pass |
| Executed-program feedback inside skills | Old versus corrected skills with the same model/settings/budget | Higher valid CAD IoU, fewer invalid selected answers, fewer repeated failed actions, acceptable runtime overhead |
| Useful revolve feedback and axis suggestions | Corrected skills with/without that interface change | Better executed-CAD reconstruction on a separately reported axisymmetric stratum; successful proposals and accepted improvements per call |
| Shared-interface deterministic policy and section-only ablation | Code, code+section, full skills, deterministic policy | Establish which tools add value and whether LLM decisions improve on the policy at comparable cost |

A useful **development diagnostic**, not a new experimental result: replacing D’s invalid/unbuilt outputs with the corresponding valid A outputs raises validity-gated mean IoU from **0.8563 to 0.9145** on the existing records. This does not repair `00090768`, because it is valid. It demonstrates why both fallback retention and geometric scoring matter.

**Held-out protocol**

Treat every currently used set—including `fresh` and agent-study parts—as development data for these repairs. I verified no file-ID overlap between the current fresh cohort and the other local sets. The index still contains **835 unused benchA-hard and 940 unused benchE-hard rows** under that exclusion.

Create a new named cohort after freezing code and settings. Do not simply change the seed and refill `fresh`: [bench/fetch_cadbench.py:86](/Users/Andrewlin/CADFit/bench/fetch_cadbench.py:86) deliberately excludes that folder from its on-disk exclusion set.

Use these rules:

- **Primary metric:** mean validity-gated executed CAD IoU, with all failures counted as zero. Also report ungated CAD IoU and separate failure categories.
- **Pipeline:** paired comparisons on a fixed, balanced cohort. Approximately **300 parts** is a defensible starting point: the observed D−A paired standard deviation is 0.307, implying roughly 296 parts for 80% power to detect a 0.05 difference under a normal approximation. Recalculate this planning estimate from repaired-system development results.
- **Agents:** prioritize Gemma and Qwen3.6 before repeating all six models. Use a prespecified new subset with at least three independent episodes per condition. Bootstrap by part, preserving repeated episodes within each part; do not count seeds as independent parts.
- **Statistics:** paired, split-stratified confidence intervals for score changes; paired failure-rate analysis; multiplicity correction for declared primary comparisons. Report runtime, kernel evaluations, and tokens.
- **Judge:** retain the scoring method and sampling uncertainty for Monte Carlo cases. Small search gains should survive increased sampling precision.
- **Compute:** perform geometry repairs, replay diagnosis, and deterministic-policy work locally. Use the cluster for frozen agent comparisons when available.

The current replay checker correctly examines both the overall shape and its solids. The existing evaluation also correctly counts failures as zero and separates ungated from validity-gated scores. Those are strengths to preserve. The missing step is making those checks govern the system’s decisions.

## Memory Update

- Confirmed: mesh-only incumbent selection, decimation damage on `00729452`, missing-origin subtraction in revolve axes, and all 67 small profiles discarded on `00140273`.
- Recover fresh programs/logs before assigning exact causes to `00090768`, `00966049`, and the OCC replay failures.
- Track proposal survival from original mesh through decimation, candidate rejection, selection, and execution.
- Verify shared tool feedback, consecutive-nudge reset, deadline enforcement, and completed controls next round.
- Keep the new held-out cohort untouched throughout these repairs.

Score: 4/10
Verdict: not ready

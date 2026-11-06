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

---

# run_20261019_e1c2d949 / Round 1 — Score: 4/10

Codex gpt-6-astra xhigh, thread 01a15522-2119-7033-b0b4-d4a27983fd3f (fresh thread; previous run stale). Memory as supplied: sha256 d908a6b1…3008f.

### Raw Reviewer Response (verbatim)

Score: 4/10
Verdict: not ready

**Hold the held-out evaluation until the defects below are fixed.** There is real progress, including a documented valid reconstruction rescue, but v2 still has reproducible correctness failures and an unfinished evaluation path.

I inspected the supplied diff, implementation, paper sources, and raw results. I used in-memory probes, including actual CadQuery execution; the read-only workspace prevented a full pipeline or pytest rerun.

1. **The agent’s execution cache can return another model’s result.**

   [CadWorkspace._exec()](/Users/Andrewlin/CADFit/agent/cad_tools.py:238) keys its cache by `tuple(id(s) for s in steps)`. Removing a step frees its dictionary; Python can immediately reuse that address for a different step. The cache retains the address, not the object.

   I reproduced this through the actual `add_code → remove_step → add_code` methods, mocking only replay/I/O and supplying controlled scores:

   - Base: executed score 0.90.
   - Rejected trial: executed score 0.10.
   - Remove trial, add an improvement with score 0.99.
   - The new step reuses the old ID. Its returned `program_iou` is **0.10**, and no replay occurs. The retained executed answer remains 0.90.

   This corrupts feedback and can suppress improvements during ordinary exploration. Separately, [episode metadata](/Users/Andrewlin/CADFit/agent/agent_loop.py:472) reports steps and sources from `ws.best`, although v2 exports `ws.best_exec`; reported program composition can therefore describe a different answer.

   **Minimum fix:** assign each added step a monotonically increasing identifier and use those identifiers for caching. Generate answer metadata from the selected executed answer. Add the add/remove/add regression above. The lexicographic **validity-first best-answer comparison itself is correct**; its cache inputs are not reliable.

2. **Pipeline selection explicitly contradicts the validity-gated objective.**

   [exec_verify.choose()](/Users/Andrewlin/CADFit/exec_verify.py:141) selects an invalid program whenever its IoU exceeds the best valid program by more than 0.005. A valid 0.90 reconstruction loses to an invalid 0.99 reconstruction, turning a primary score of 0.90 into **zero**.

   This is an intentional rule, not an obscure numerical case. It also contradicts the pipeline flag’s “best valid” description. **None of the eight completed local v2 records exercised this branch**, so I am identifying a demonstrated selection-rule defect, not claiming an observed aggregate regression.

   The failure path also weakens the delivery guarantee: when verification finds no built program or raises, [run_pipeline.py](/Users/Andrewlin/CADFit/run_pipeline.py:1317) leaves the previous mesh/program pair and mesh score in place. An independent `--cad` evaluation can catch this; `final_iou.json` alone cannot certify execution-verified delivery.

   **Minimum fix:** always prefer the highest-scoring valid program when one exists. If none exists, explicitly record a failed validity-gated result; keep diagnostic meshes separately identified.

   **What is correct:** comparing candidates with the target mesh is **not target leakage** here—the mesh is the reconstruction input. On successful selection, the pipeline copies the chosen program and its executed tessellation. Fused rewrites and skipped failed cuts are legitimate alternative candidates when their resulting geometry is actually scored.

   There is concrete positive evidence: the saved [00642725 verification record](/Users/Andrewlin/CADFit/bench/runs/dev2_v2/00642725_384f51542e8a1ea67d2847ef_step_003/final_iou.json:12) reports an original program with 208 solids, 34 invalid, and IoU 0.000898; the fused variant has one valid solid and IoU **0.937546**. That supports this repair on one case.

3. **The deadline implementation still fails, and the comparison changes stopping behavior along with tools.**

   The new [SIGALRM wrapper](/Users/Andrewlin/CADFit/agent/agent_loop.py:308) does not establish the claimed deadline:

   - [Axis refinement catches `Exception`](/Users/Andrewlin/CADFit/greedy_search.py:305), including the alarm’s `TimeoutError`, and continues. With injected delays in this real path, a 0.02-second deadline returned successfully after 0.144 seconds. The one-shot alarm had already been consumed.
   - During [candidate subprocess execution](/Users/Andrewlin/CADFit/cadquery_ops.py:661), cleanup handles `subprocess.TimeoutExpired`, but not the propagated alarm exception. A controlled probe returned a session-timeout error while its child process remained alive. I explicitly terminated that probe child.
   - [The scripted policy](/Users/Andrewlin/CADFit/agent/scripted_skills_policy.py:51) neither sets `ws.deadline` nor uses the new tool deadline wrapper. Its time limit remains a check between calls.
   - The policy’s v2 acceptance decision still uses mesh `iou_after − iou_before`, checking executed validity but ignoring executed-IoU improvement.

   **Minimum fix:** propagate session timeout exceptions through the relevant geometry handlers; clean up candidate processes on every interrupted exit; enforce the same remaining deadline for agents and policy. Under v2, make policy acceptance use executed-program quality.

   **The nudge reset is correctly implemented.** However, `CADFIT_AGENT_EXEC` changes feedback, assembly, answer selection, prompting, nudge behavior, and timeout handling together. That comparison measures the **whole v2 configuration**. To attribute gains specifically to tools, use the same corrected harness in both conditions; otherwise label the package comparison honestly.

4. **The revolve-origin correction is right; the new “deepest crossing” safeguard is incomplete.**

   Subtracting the plane origin before transforming the world-space axis is correct. The subsequent [emission check](/Users/Andrewlin/CADFit/cadquery_ops.py:466), however, examines selected coordinate pairs extracted by regex. It ignores circle radii, arc endpoints beyond the first pair, and curve extrema. It therefore cannot guarantee that the emitted profile lies on one side of the axis.

   This occurs in a saved v2 proposal, not merely a synthetic construction. In [00941601’s refinement, sketch 9](/Users/Andrewlin/CADFit/bench/runs/dev2_v2/00941601_071d956501ffc009e947b4d3_step_000/refine_under_1/precomputed_operations.json:7879):

   - Circle center x: **112.98129**
   - Radius: **112.68804**
   - Leftmost x: **0.29325**
   - Emitted vertical axis x: **0.294312**

   The circle crosses the axis by **0.001062**. Executing the emitted program produced `Standard_Failure: BRep_API: command not done`. Moving the axis outside the actual circle made it build, but produced a gigantic solid—volume approximately **28.25 million** in normalized coordinates. That is evidence of a bad fitted profile, not a useful candidate to rescue by moving its axis.

   **Minimum fix:** check the actual emitted curves, including their extrema. Restrict axis adjustment to numerical tolerance; refit or reject profiles requiring substantive alteration. Add this stored failure and a rotated, translated shaft regression. The existing offset-shaft test checks reported axis metadata and precision; it does not establish correctness of all emitted axes.

5. **The held-out cohort is sound, but the evaluation is not yet runnable and fully controlled.**

   Several checks pass:

   - Every stored top-level Python file in `dev2_d0_code` matches `e260397`.
   - In the supplied commit diff, dx disables both revolve changes and otherwise adds execution verification to d0’s configuration. This isolates the **verification/rewrite/fallback package**, not verification alone.
   - fresh2 contains **300 files**, exactly **150 benchA + 150 benchE**, with no file-ID overlap against other local cohorts.
   - Seeded selection reproduces the downloaded file lists. The planned 20-part agent subset contains **8 benchA and 12 benchE**. Three episodes per condition is sensible; it remains 20 independent parts.

   But there are concrete problems before launch:

   **The agent scorer breaks on fresh2.** [agentsk_score.py](/Users/Andrewlin/CADFit/bench/agentsk_score.py:126) still loads `fresh_scores.json` and `fresh_section_control.json`. Its direct `sc[p]` lookup raises a `KeyError` for fresh2 IDs; I reproduced that lookup without inspecting held-out geometry.

   **The pipeline scorer can omit unstarted parts.** [score_runs()](/Users/Andrewlin/CADFit/bench/score.py:268) only records a missing reconstruction when its part directory exists. Parts never launched after an interrupted job can disappear from the denominator. The acknowledged partial local run illustrates why completion checks matter: I found **11 completed d0 records and eight completed v2 records**, not a completed paired cohort.

   **The source freeze is incomplete.** [v2_submit.sh](/Users/Andrewlin/CADFit/bench/v2_submit.sh:16) snapshots top-level pipeline modules, while agents and replay/judge code use the live checkout. During this review, an uncommitted `fit_primitives.py` arc correction appeared outside the supplied diff. Copying that into dx introduces a geometry change relative to d0. Existing snapshots, newly copied snapshots, and live agents would then use different code.

   **Minimum fix:** wire scoring to the actual h2 references; require results/status for the entire declared manifest before analysis; freeze the complete source used by jobs and scoring after repairs. Preserve dx’s intended intervention explicitly. Smoke-test the scoring path before spending held-out compute.

   Prespecify primary contrasts and multiplicity handling, bootstrap by part within split, and keep repeated episodes together. Preserve CAD scoring method and Monte Carlo uncertainty—the current verifier discards the judge’s method, and the CAD scorer retains only its scalar IoU.

6. **The strongest improvements and the paper’s central controls remain unfinished.**

   The current pipeline verifies a small final shortlist. It does not preserve the best valid executed incumbent throughout search, and an earlier stage failure can prevent verification altogether. Moreover, `--score-original` fixes the main search input, while [residual construction and refinement acceptance](/Users/Andrewlin/CADFit/run_pipeline.py:1081) still use the decimated mesh.

   The raw development results suggest the following priorities:

   - **Retain a valid fallback early.** Execute original-mesh section proposals and promising simple candidates before expensive composition. Preserve that incumbent through search failure. Recomputing the earlier diagnostic—substituting A only where D is invalid/unbuilt—raises D’s development validity-gated mean from **0.8563 to 0.9145**. This is diagnostic headroom, not an achievable-performance estimate.
   - **Make refinement and tool feedback consistent with executed geometry.** Use the original target for authoritative residuals and acceptance. Align model sections, reported scores, and selected-answer metadata. Report which assembly operation failed, rather than only a generic build failure.
   - **Repair proposal failures before widening search.** Thin-part sections, reliable small profiles, and rejection/refitting of malformed curves have direct evidence behind them. More beam width or more model calls currently spend compute around these defects.

   The paper still has [pending controls and repeats](/Users/Andrewlin/CADFit/paper/numbers.tex:400). The new submission script runs skills-only v1/v2 comparisons; it does not complete the code-versus-section-only-versus-full-skills attribution study. [NARRATIVE_REPORT.md](/Users/Andrewlin/CADFit/NARRATIVE_REPORT.md:128) also still concludes that tools rather than planning explain most gains from a nonsignificant agent-policy comparison. That inference is unsupported.

   **Minimum fix:** complete the focused controls with corrected tools and common budgets, or narrow the claims. Clearly separate historical pre-v2 findings from development repairs and future held-out results. The current evidence supports a useful implementation audit; it does not yet establish a convincing top-venue methodological contribution.

## Memory Update

- Confirmed new defects: execution-cache aliasing after step removal; invalid-preference verifier selection; swallowed deadline exceptions; surviving candidate subprocesses; unmatched policy deadlines; incomplete revolve curve-crossing checks; fresh2 agent-scoring `KeyError`.
- Verified improvements: world-to-local origin subtraction, original-input routing for main sections/scoring, consecutive-nudge reset, validity-first agent retention logic, and the recorded fused rescue of `00642725`.
- Verified controls at the supplied revision: d0 source matches `e260397`; dx disables revolve changes; fresh2 is balanced, complete, and ID-disjoint.
- Local v2 evidence remains eight completed, selection-biased records. No aggregate v2 efficacy conclusion is justified.
- Track the concurrent `fit_primitives.py` edit separately from the reviewed diff and existing snapshots.
- Next round: regression evidence for these defects, complete dev-cohort replay, corrected scoring/protocol, then frozen held-out evaluation. Keep fresh2 outcomes untouched during repairs.

---

## Run run_20261026_b59bde60 — Round 1 — Score: 4/10

### Raw Reviewer Response (verbatim)

Score: 4/10
Verdict: not ready

**There is genuine engineering progress, but the current artifacts do not establish the paper’s three intended claims: improved validity-gated CAD fidelity, improved surface detail, and better time efficiency. Keep fresh2 held out for now.**

I recalculated the supplied results, inspected the current implementation, and ran in-memory geometry probes. The dev3/dev4 reconstruction folders and agent transcripts are absent locally, so I could verify their score arithmetic but not replay those entire studies. Full pytest was blocked by the read-only environment’s cache restrictions; isolated probes did run.

Several previous concerns were genuinely addressed:

- Execution caching now uses program text, eliminating the demonstrated object-ID aliasing. Answer composition metadata uses the delivered answer.
- `exec_verify.choose()` now always prefers a valid program. My valid-versus-invalid selection probe passed.
- The new deadline exception survives ordinary `except Exception` handlers; the isolated interruption probe passed. Candidate execution now cleans up its process group on interruption.
- The stored oversized-circle revolve failure is now rejected.
- **The repair result is real:** executing the saved `00232213` programs changed an invalid shape containing two invalid solids into a valid shape with no invalid solids and essentially unchanged volume.
- The unsupported “tools rather than planning explain the gains” inference has been removed.
- fresh2 has 300 distinct parts, balanced 150/150, with no overlap against the other local manifests—including by source-part prefix.

Those are substantive fixes, not cosmetic responses.

1. **The latest effectiveness numbers still cannot support a clean causal claim.**

   Recomputed directly from [dev34_scores.json](/Users/Andrewlin/CADFit/results/dev34_scores.json):

   | Run | Mean validity-gated CAD IoU | Valid deliveries |
   |---|---:|---:|
   | dev3_d0 | 0.80798 | 52/60 |
   | dev4_dx | 0.91998 | 58/60 |
   | dev4_v2 | 0.94892 | 59/60 |

   These are **old-judge development results**, spanning code revisions and unstable execution outcomes. Approximately **79% of the d0→v2 gated improvement comes from parts where d0 did not deliver valid CAD**. Validity recovery is valuable; this decomposition does not invalidate it. It does prevent presenting the gain as primarily better geometric reconstruction.

   The additional v2−dx improvement is **0.02894**, with an exploratory paired bootstrap interval approximately **[−0.0013, 0.0744]**. The current evidence therefore does not establish that the geometry-fix package improves the mean beyond execution verification, rewriting, repair, and fallback selection.

   The paper also remains centered on the older A–D experiment. Its original held-out status can be described historically, but this same cohort is now development data for v2. Moreover, [numbers.tex](/Users/Andrewlin/CADFit/paper/numbers.tex:400) still contains pending controls and repeats that the prose describes as completed.

   **Minimum fix:** finish the complete, controlled dev5 matrix under common infrastructure and the corrected judge; rescore historical outputs; retain programs, replay records, and execution logs. Rewrite the manuscript around the resulting evidence and distinguish historical evaluation from subsequent development. Do not retrospectively exclude OOM failures: use a consistent retry/resource policy across arms and retain unresolved failures as zeros.

   Before final analysis, explicitly check manifest completeness. [score_runs()](/Users/Andrewlin/CADFit/bench/score.py:288) now correctly counts never-started parts within a recognized run, but still omits actively running parts and summarizes the common subset. That output is useful for monitoring, not automatically a completed experiment.

2. **The top-venue contribution remains insufficiently differentiated.**

   Executing proposals, using geometric feedback, and protecting a valid incumbent are already central to [CADFather](https://arxiv.org/html/2610.09127v1). Kernel-level validity feedback is also present in [CADSmith](https://arxiv.org/html/2603.26512v1). Neither “execute the program” nor “give an LLM CAD tools” is independently a convincing methodological novelty claim.

   The potentially valuable contribution is narrower: **a controlled demonstration of how mesh-based optimization misrepresents delivered CAD, which interventions repair that discrepancy, and what an LLM contributes beyond inexpensive geometric policies.** The decisive controls for that story remain unfinished.

   **Minimum fix:** choose that focused scientific question and complete its controls. Separate the execution/repair package from additional geometry changes, and include the cheap section-only/best-of control. If claiming competitive reconstruction performance, add a contemporary external method such as CADFather under your evaluator. If keeping this strictly an audit of one optimizer family, narrow the claims accordingly; that is presently a more plausible workshop/tooling paper than a strong NeurIPS/ICML submission.

3. **The agent study does not yet identify the benefit of the full tools or of LLM decisions.**

   The historical skills-versus-code result is substantial. However:

   - Code+section-only attribution remains pending.
   - The corrected shared-interface scripted-policy result remains pending.
   - Repeated episodes remain pending in the manuscript.
   - The six-model results concern the earlier tool/harness configuration.
   - Qwen3.8’s large sensitivity to its token allowance shows that harness configuration materially affects the comparison.

   The revised narrative correctly treats the nonsignificant agent–policy comparison as inconclusive. Preserve that restraint: it establishes neither equivalence nor absence of a planning contribution.

   **Minimum fix:** on the corrected common harness, compare **code, code+section, full skills, and the shared-interface deterministic policy**. Start with the strongest relevant open model before multiplying model configurations. Use repeated episodes and report validity-gated scores. Opus/Sonnet should extend this controlled comparison after development calibration; their presence alone will not repair the missing attribution.

4. **Execution feedback and recovery are still only partially aligned with the advertised objective.**

   In [CadWorkspace._exec()](/Users/Andrewlin/CADFit/agent/cad_tools.py:290), a successful manifold conversion is scored with `self._score(m)`. The corrected `score.robust_iou()` is reached only when that conversion fails. Since `_cached_manifold()` can repair or alpha-wrap geometry, this is not generally the same objective as the independent judge. Consequently, the executor log’s assertion that the judge correction also fixes agent feedback is too broad.

   I am **not** claiming the previous 0.13 discrepancy necessarily persists in agents. On `00966049`, I verified that the agent’s target conversion successfully repairs the cracks and agrees essentially exactly with the normalized STEP tessellation. The confirmed issue is the inconsistent scoring path, not an established new aggregate regression.

   Two earlier limitations also remain:

   - Agent `section()` still displays the mesh composition, whereas `evaluate()` can describe executed geometry.
   - Pipeline verification remains a final-stage shortlist operation. [Early analysis failure returns before verification](/Users/Andrewlin/CADFit/run_pipeline.py:1075), so adding late alternatives does not implement an incumbent that survives search failure. Refinement residuals also still originate from the decimated input.

   **Minimum fix:** use the declared executed-CAD criterion for authoritative answer selection, or explicitly label the internal score as a surrogate and avoid external-score guarantees. Make model-section feedback describe the same geometry. Either retain an executed fallback before expensive search, or accurately describe the method as final-stage verification with possible no-output failures. The latter is scientifically acceptable when failures remain in the denominator.

5. **The runtime evidence supports trade-offs, not a general efficiency advantage.**

   From [runtime_raw.json](/Users/Andrewlin/CADFit/results/runtime_raw.json), mean minutes on the same 20 parts are:

   | Configuration | Basic tools | CADFit tools |
   |---|---:|---:|
   | Gemma-4-31B | 27.69 | 19.41 |
   | Qwen3.6-35B | 5.62 | 5.58 |
   | gpt-oss-20b | 4.92 | 5.53 |
   | Qwen3.8-27B | 18.92 | 24.11 |

   The dev4_v2 pipeline averages **8.70 minutes** on those parts. Thus tools sometimes reduce elapsed time and sometimes increase it; the pipeline is not universally faster than agents.

   More importantly, [the agent runner defaults to eight simultaneous episodes sharing one model server](/Users/Andrewlin/CADFit/bench/agentsk_run.py). Episode latency therefore includes contention. Pipeline runs use another concurrency/resource configuration. These measurements are valid observations of those deployments, but not hardware-neutral algorithmic speed comparisons.

   The new setup/model/tool instrumentation is useful, but those fields are absent from the supplied historical timing records. One historical Gemma code episode also lasted **34.16 minutes**, so “30-minute cap” requires qualification.

   **Minimum fix:** measure the final configurations with declared hardware and concurrency. Report latency separately from throughput; include setup, geometry tools, execution verification, and answer delivery. Pair quality with time, report medians and tails, and count failed-attempt time. Use quality-versus-time curves or time to a prespecified quality target for an efficiency claim. Report API cost separately for closed models.

6. **“Detail recovered” currently conflates valid delivery with finer geometric fidelity.**

   The detail results are informative, but their strongest interpretation is narrower than the label.

   On the **52 parts valid in both runs**, I obtain:

   | Surface metric | d0 | v2 |
   |---|---:|---:|
   | Target surface within 0.5% of part size | 0.98225 | 0.98153 |
   | CAD surface within that tolerance of target | 0.92064 | 0.94079 |
   | F-score | 0.94671 | 0.95812 |

   The all-part gated recall rises **0.85128→0.96421**, but essentially all that increase comes from newly valid deliveries. Conditional recall does not improve. There is a legitimate smaller improvement in surface precision and F-score.

   A one-sided proximity threshold also does not establish that particular pockets, ribs, or shallow features were reconstructed. The actual v2 result for `00046097` illustrates why both directions matter: recall is **0.889**, but precision is only **0.492**.

   **Minimum fix:** call this *surface agreement at a stated tolerance*, and report recall, precision, and F-score together. Keep all-part gated results primary and common-valid comparisons explicitly diagnostic. Add a small prespecified tolerance sweep and sampling/tessellation convergence check. Stronger claims about recovering fine features need feature-sensitive evidence; otherwise narrow the wording.

**Of the planned method changes:**

| Change | Recommendation for this paper |
|---|---|
| Snap extrusion extents to detected planes | **Highest priority.** It directly addresses dimensions poorly resolved by the current translation grid. Use original-input planes and retain the unsnapped alternative until executed scoring selects between them. |
| Restrict translation search to the part extent and refine coarse-to-fine | **Worth doing.** A plausible accuracy/runtime improvement. Compare candidate quality, final gated score, and time against the existing sweep. |
| Silhouette trimming | **A development experiment, not yet a required ingredient.** Use actual projected silhouettes; extruding a middle cross-section can remove legitimate off-section material. Execute and validate the trimmed candidate, retaining the incumbent. |
| Occupancy-bitset IoU | **Defer unless profiling identifies composition scoring as a major bottleneck.** It changes the search approximation. Any speed claim needs resolution/seed convergence and independent final CAD scoring, particularly on thin parts. |

An early valid fallback is more directly motivated by the observed failure pattern than adding another approximate search objective.

**The final evaluation protocol should be:**

- **Development first:** complete dev5, settle judge/feedback semantics, finish the essential controls, and select any method changes using the existing 60 parts. No fresh2 outcome inspection during this process.
- **Freeze the actual experiment:** source, arm definitions, model identifiers/settings, budgets, resources, and retry rules. Ensure the d0 source includes the intended common infrastructure fixes; the current submission script still defaults to the older d0 revision.
- **Pipeline:** run the paired 300-part cohort, reporting the two splits separately and the balanced aggregate. Include d0, dx, v2, and a cheap executed section/best-of reference. First repeat development stress cases under several fixed seeds/runs. If material run variability remains, repeat the final comparisons; one seed cannot support claims of run robustness.
- **Agents:** prespecify a stratified subset and use at least three independent episodes per stochastic condition. Twenty parts can detect the large historical tools effect but may poorly resolve agent-versus-policy differences. Choose additional parts from a power/precision calculation on development data; more episodes do not substitute for more independent parts.
- **Statistics:** make mean validity-gated CAD IoU primary, with every attempted part represented. Use paired, split-stratified intervals, keeping all episodes of a part together. Report paired validity changes and prespecify the primary comparison family. Treat superiority and equivalence as different hypotheses.
- **Measurement:** retain judge method, union-sample count, and uncertainty. Check small claimed differences with higher-precision evaluation and independent sampling. State the occupancy convention for open targets—the current development cohort contains five, despite the draft’s watertight-input description.
- **Timing and detail:** evaluate the same final programs and configurations used for the quality claims. Publish the programs and replayable records underlying the tables.

**No go for fresh2 yet.** The release condition is a complete, interpretable development experiment with the final measurement protocol—not implementation of every proposed enhancement.

## Memory Update

- Confirmed fixed: object-ID execution-cache aliasing, invalid-preference selection, delivered-answer composition metadata, ordinary-handler swallowing of session deadlines, candidate-process cleanup path, and rejection of the stored oversized-circle revolve failure.
- Independently replayed `00232213`: original invalid with two invalid solids; repaired valid with essentially unchanged volume.
- Recomputed old-judge gated means: d0 **0.80798**, dx **0.91998**, v2 **0.94892**. Approximately **79%** of d0→v2 improvement comes from newly valid deliveries; v2−dx remains inconclusive.
- Surface recall is unchanged on common-valid parts; surface precision and F-score improve modestly. Gated recall improvement primarily measures validity recovery.
- Remaining implementation limitations: agent execution scoring bypasses the corrected judge on its normal path; model sections can show different geometry from execution feedback; pipeline fallback verification remains late.
- Remaining evidence gaps: complete dev5, corrected rescoring, matched policy, section-only attribution, repeated agent episodes, final-configuration timing, and locally available full reconstruction/trajectory artifacts.
- fresh2 remains balanced and disjoint. Keep outcomes untouched until the development validation and experiment freeze are complete.


---

## Run run_20261026_b59bde60 — Round 2 — Score: 5/10

### Raw Reviewer Response (verbatim)

Score: 5/10
Verdict: not ready

**The validity-recovery result is now credible development evidence. The surface-fidelity measurement and the claimed precise-extents implementation still have demonstrable defects.** I would reject the current submission, but several earlier concerns have genuinely been addressed.

I independently recalculated the results, reran the paired analysis, inspected the changed code, and ran isolated in-memory probes. The full dev5/dev6 reconstruction folders are absent locally, so this is not a complete replay of those experiments.

From the supplied [pipeline results](/Users/Andrewlin/CADFit/results/dev345_scores.json), [dev6 comparison](/Users/Andrewlin/CADFit/results/dev6_scores.json), and [post-hoc trim results](/Users/Andrewlin/CADFit/results/dev6_v3_trim.json):

| Configuration | Mean validity-gated CAD IoU | Valid deliveries |
|---|---:|---:|
| dev5 d0 | 0.84376 | 54/60 |
| dev5 dx | 0.93929 | 60/60 |
| dev5 v2 | 0.95636 | 60/60 |
| dev6 v2 | 0.95235 | 60/60 |
| dev6 v3, as implemented | 0.95465 | 60/60 |
| dev6 v3 + post-hoc trim | 0.95837 | 60/60 |

Several fixes are substantive:

- Agent executed-program ranking now calls the corrected `score.robust_iou`.
- The pipeline now attempts an executed fallback on ordinary analysis failure or missing search output. This is useful failure recovery, though not a persisted incumbent that survives process termination.
- The submission script applies the common infrastructure patch to d0.
- Silhouette trimming uses actual projected triangle silhouettes, executes the intersection, checks validity, and retains the incumbent when preferable.
- The section-only control averages **0.84475**, versus **0.95636** for dev5 v2, with no section-only wins exceeding 0.005. That earlier objection is answered for this cohort.
- Moving from sampled-neighbour distances to point-to-triangle distances addresses the demonstrated surface-distance convergence problem. Unfortunately, it does not fix which surface is being measured.

**Remaining Weaknesses and Minimum Fixes — ranked**

**1. The surface metric remains representation-dependent and can credit buried faces.**

There are two defects in [detail_scores.py](/Users/Andrewlin/CADFit/bench/detail_scores.py:50):

- Recall queries distances against **all CAD triangles**, including internal faces buried inside the occupied union.
- Precision bypasses boundary filtering whenever `cad.body_count <= 1`. STL vertex merging can make a multi-solid compound satisfy that condition.

This occurs on repository artifacts. I executed the saved [00232213 repaired program](/Users/Andrewlin/CADFit/bench/figures/v2_2026-10-23/inputs/00232213_repair.py). It produces **139 valid solids**, but its tessellation after an STL roundtrip has `body_count == 1`. Consequently, the filter is skipped. Of 10,000 sampled points, **1,645 fail the evaluator’s own boundary test**. Applying that test changes estimated precision at τ=0.01 from **0.9105 to 0.9271**.

The repository’s [stacked-box regression](/Users/Andrewlin/CADFit/tests/test_v2_fixes.py:261) exposes the recall problem particularly clearly. It explicitly expects recall near one after adding a slab that buries an original exterior face. Using that construction, I obtained:

| Same occupied CAD geometry | Recall | Precision | F-score |
|---|---:|---:|---:|
| Stacked boxes retaining internal faces | 1.0000 | 0.6506 | 0.7883 |
| Equivalent union boundary | 0.7223 | 0.5068 | 0.5957 |

These are 10,000-sample diagnostic estimates; sampling uncertainty cannot explain this difference.

**Minimum fix:** measure both directions against the boundary of the occupied CAD union, preserving cavities. Do not use connected-body count as proof that internal faces are absent. Replace the incorrect stacked-box expectation with a representation-invariance regression, include the saved compound case, and recompute surface results. If that cannot be measured consistently, remove the surface-fidelity claim.

This correction needs **rescoring**, not another pipeline search.

**2. Cap-plane snapping and its unsnapped alternatives never reach the production search.**

[Translation analysis saves the per-sketch JSON](/Users/Andrewlin/CADFit/analyze_loop_translation.py:494) before [snapping the returned intervals](/Users/Andrewlin/CADFit/analyze_loop_translation.py:747). [Candidate generation reloads that earlier per-sketch file](/Users/Andrewlin/CADFit/greedy_search.py:39).

I reproduced the actual producer/consumer path with file IO held in memory:

| Plate thickness | Returned snapped endpoint | Endpoint reloaded by search |
|---|---:|---:|
| 0.0063 | 0.0063 | 0.0060 |
| 0.4137 | 0.4137 | 0.4200 |

The reloaded intervals also lack `t_start_grid` and `t_end_grid`, so the intended grid-end alternatives are unavailable. The new test passes because it examines the returned object, not the data consumed by candidate generation.

Thus **dev6 measures the restricted/finer sweep and associated interval changes, not the advertised snapping mechanism**. Its +0.00231 gain cannot substantiate snapping.

**Minimum fix:** persist the finalized intervals, and test through reload and candidate generation. Repeat the affected development comparison and trim evaluation on the corrected outputs. Historical d0/dx results do not need rerunning merely because this path changes.

**3. The proposed v3/v4 held-out launch is not fully frozen.**

[v2_submit.sh](/Users/Andrewlin/CADFit/bench/v2_submit.sh:49) freezes only d0, dx, v2, and the shared source tree, despite accepting configurable `ARMS`.

If v3/v4 are requested, [run_parallel_arms.sh](/Users/Andrewlin/CADFit/bench/run_parallel_arms.sh:89) creates their missing snapshots by copying only top-level Python files. [exec_verify.py](/Users/Andrewlin/CADFit/exec_verify.py:42) then falls back to the live checkout for replay/judge code.

This recreates the incomplete-freeze problem specifically for the newly proposed arms. The default d0/dx/v2 path has improved; the extension has not inherited that guarantee.

**Minimum fix:** freeze every requested arm’s complete source before submission, including its replay/judge dependencies. Verify the actual v3/v4 launch path on development inputs. No additional framework is needed.

**4. The evidence supports reliability recovery much more strongly than a new reconstruction method or better detail.**

The rerun analysis gives:

- **dx−d0:** +0.09554, nominal paired 95% CI **[+0.03160, +0.17383]**.
- **v2−d0:** +0.11260, **[+0.04373, +0.19328]**.
- **v2−dx:** +0.01706, **[−0.00039, +0.04542]**.
- **Current v3−v2:** +0.00231, **[−0.00012, +0.00530]**.

Approximately **82% of dx’s gain** and **75% of v2’s gain** come from parts where d0 delivered no valid CAD. That is a valuable result. It is a different result from substantially improving already-valid reconstructions.

The existing surface results likewise show no demonstrated advantage on the 54 commonly valid parts: mean F-score at τ=0.01 is approximately **0.9715–0.9732** across configurations. Those numbers need correction under finding 1; even taken at face value, they do not establish equivalence or improved detail.

Trim is promising: its post-hoc no-trim scores exactly reproduce all 60 dev6-v3 scores, and its mean increment is **+0.00371**. However, “no losses” follows from retaining the higher-scoring candidate under the selection judge. It is not independent evidence that geometric accuracy never decreases.

Novelty also remains constrained. Executed proposals, geometric feedback, and protected valid candidates are already central to [CADFather](https://arxiv.org/html/2610.09127v1). Kernel-based validity feedback also appears in [CADSmith](https://arxiv.org/html/2603.26512v1). Neither executing programs nor exposing CAD tools is sufficient novelty by itself.

**Minimum fix:** make reliable finalization and the measured mesh/program discrepancy the central contribution; establish its effect on untouched parts. Complete the CADFather comparison under the common judge before making competitive-performance claims. Report which delivery alternatives supply the gains. A full factorial ablation of every repair is unnecessary.

**5. Agent attribution and time efficiency remain unfinished.**

The pending code/code+section/skills repeats and matched scripted policy are still necessary for the agent claim. Historical six-model results cannot substitute for controls under the corrected harness.

The supplied [runtime file](/Users/Andrewlin/CADFit/results/runtime_raw.json) contains pipeline records for **dev3_d0 and dev4_v2**, not the final dev5/dev6 configurations. It therefore does not establish the cost of the current method, snapping, or trimming.

There is also unresolved run variability. Dev5-v2 versus dev6-v2 changes the mean by −0.00401, including a **−0.2991** change on `00247424`. Different code versions prevent treating this as a clean repeatability experiment. Nevertheless, it makes single-run improvements of a few thousandths unpersuasive. The runner’s `--seed 0` is not end-to-end determinism: revolve analysis still samples without using that seed.

**Minimum fix:** finish the three matched agent conditions and policy repeats; measure the final pipeline configurations on the same comparison parts with recorded resources, concurrency, budgets, and retry costs. Include verification and trimming in end-to-end time. Report quality alongside latency and resource use. If resources differ, describe deployment latency rather than an algorithmic speedup.

Opus/Sonnet are **not required** to resolve these deficiencies.

**Freeze and release decision**

**Not yet for the advertised v3/v4 matrix.** The d0/dx/v2 development question is mature enough; the remaining prelaunch work should be bounded:

1. Fix the snapped-interval persistence and complete-source launch defects.
2. Run the corrected development comparison, including end-to-end timing and a small integrated trim check.
3. Establish the repeat protocol on unchanged code, then freeze the method and evaluation choices.

Do not require a significant development p-value before testing a frozen hypothesis. Do not add more optimizations while waiting.

My recommended held-out matrix is:

| Arm | Purpose |
|---|---|
| d0 + common infrastructure fixes | Historical method reference |
| dx | Execution-verified delivery package |
| v2 | Additional geometry corrections |
| Corrected v3 | Extent/sweep package |
| Corrected v3 + trim | Final package and incremental trim comparison |
| Executed section-only control | Cheap geometric reference |

Trim can be evaluated as a final stage on each saved v3 delivery, preserving the paired comparison, while separately measuring its actual added time.

If you decide **before seeing fresh2 outcomes** to omit v3/trim from the main method, I would release the narrower **d0/dx/v2/section-only** experiment after freezing its settings. Missing agent and CADFather results need not delay an independently frozen pipeline experiment.

The surface evaluator can be corrected while pipeline outputs are being generated, provided its definition is settled before examining held-out surface comparisons.

**Final evaluation protocol**

- Use all **300 paired parts**, report both splits and the balanced aggregate, and count failures in the denominator. Apply the same declared infrastructure retry policy to every arm.
- Use three independent runs for comparisons supporting the small incremental improvements. Average runs within part; bootstrap parts within split while retaining their repeated measurements together. Do not select each part’s best run.
- Prespecify dx−d0 as the reliability contrast, with v2−dx, corrected-v3−v2, and trim−v3 as secondary contrasts. Match multiplicity correction to the actual hypothesis: Holm-corrected **sign tests do not correct confidence intervals for mean differences**.
- Report validity changes, gated IoU, conditional fidelity, and failure types separately. Common-valid subsets are diagnostic, not substitutes for the primary denominator.
- Validate small Monte Carlo-based gains with independent, higher-precision final evaluation. Keep selection decisions fixed during that check.
- Keep agent episodes clustered by part. Three episodes on 20 parts remain **20 independent parts**, not 60.
- Freeze any CADFather held-out comparison subset before looking at pipeline outcomes.

Of the method changes, **finish the snapping integration and retain trim as a modest secondary experiment**. The restricted/finer sweep deserves its paired accuracy/runtime comparison. Defer occupancy-bitset scoring: the present paper does not need another approximate objective.

**Central claim**

The defensible development-stage framing is:

> In the audited CADFit search family, final-program execution, kernel-validity checks, and selection among repaired or fallback programs substantially improve valid delivery and expected validity-gated fidelity. Most of the observed improvement comes from recovering failed or invalid outputs; additional geometric refinements provide smaller, currently uncertain gains.

The agent study should then ask how much additional value a learned controller supplies over the same geometric tools and budgets.

Do not currently claim improved fine-detail recovery, established surface equivalence, superior planning, or general time efficiency. The draft still describes the earlier experiment; its abstract, cohort description, generated results, and conclusions need to be rebuilt around the final frozen study.

## Memory Update

- Reviewed HEAD `80cb5f1`; independently recalculated aggregates and reran paired development analysis. Full dev5/dev6 programs were unavailable locally.
- Confirmed dev5 gated means: d0 **0.84376**, dx **0.93929**, v2 **0.95636**; valid deliveries **54/60, 60/60, 60/60**. Approximately **75%** of d0→v2 gain comes from newly valid deliveries.
- Confirmed agent executed-score routing to the corrected judge, ordinary-failure executed fallback, common d0 infrastructure patch, and genuine projected-silhouette trimming.
- **New confirmed integration defect:** per-sketch intervals are saved before snapping; search reloads unsnapped endpoints without grid-alternative fields. Current dev6 does not test cap-plane snapping.
- **New confirmed measurement defects:** recall credits internal faces; precision skips filtering for merged single-component STLs. Saved `00232213_repair.py` produces 139 solids but `body_count == 1`; 16.45% of sampled points fail the evaluator’s own boundary test.
- Repository stacked-box test currently codifies incorrect boundary recall. Equivalent occupied geometry scored approximately **0.788 versus 0.596 F-score** depending on retained internal faces.
- **New confirmed launch defect:** v3/v4 requested through `ARMS` are not fully archived; they fall back to top-level copies and live replay/judge code.
- Trim: **+0.00371**, chosen on 27/60; post-hoc no-trim scores reproduce all dev6-v3 scores. Section-only: **0.84475**, with no material wins over v2.
- Remaining scientific gaps: corrected surface measurement, incremental-method evidence, matched agent controls/policy, final-configuration timing, CADFather comparison, and unchanged-code repeats.
- Full fresh2 matrix should wait for the bounded integration/freeze fixes and corrected development validation. A deliberately narrowed d0/dx/v2/section-only study can proceed after freezing its protocol.


---

## Run run_20261026_b59bde60 — Round 3 — Score: 5/10

### Raw Reviewer Response (verbatim)

Score: 5/10
Verdict: not ready

**The pipeline development is now sufficient to freeze. I do not approve `HELDOUT_PROTOCOL.md` + `h2_submit.sh` unchanged, but I approve proceeding after the bounded amendments below.** Another round of method development is unnecessary.

Submission readiness is a separate question: held-out effectiveness, agent attribution, competitive baselines, and the final paper remain incomplete.

I reviewed HEAD `6839f03`, recalculated the supplied results, and exercised critical paths in memory. The full dev7 programs and trajectories are unavailable locally, so I could verify their score arithmetic but not replay the entire experiment.

Several earlier concerns are genuinely resolved:

- Snapped intervals now reach candidate generation. My reload-path probe produced both **0.4137 snapped** and **0.4200 grid** candidates.
- The fused-boundary path successfully turns the saved 139-solid `00232213` reconstruction into a valid, closed union. The stacked-box representations now agree within sampling uncertainty.
- Current revolve surface sampling respects the seed.
- Every requested pipeline arm now receives a complete source archive.
- Averaging repeated scores **within part** is implemented correctly.
- Trim timing includes silhouette construction, execution, and judging.

The recalculated development evidence is materially stronger:

| Configuration | Mean gated CAD IoU |
|---|---:|
| v2, three-run average | 0.95172 |
| Corrected v3, three-run average | 0.96045 |
| v3 + trim, three-run average | 0.96549 |

All **360 v2/v3 deliveries** are valid. Averaging within part:

- **v3−v2:** +0.00873, nominal paired 95% CI **[+0.00188, +0.01971]**.
- **Trim increment:** +0.00504, **[+0.00266, +0.00784]**.

These remain exploratory development estimates, but they justify a frozen held-out test.

**Remaining Weaknesses and Minimum Fixes — ranked**

**1. The promised held-out measurement path does not yet handle the final trimmed method.**

[rejudge.py](/Users/Andrewlin/CADFit/bench/rejudge.py:27) accepts ordinary `score.py` records and locates the original reconstruction’s `_cad.stl`. The trim results instead contain `chosen`, `chosen_valid`, `gated`, and nested variant records.

I tested an actual dev7 trim record for `00046097`, selected as `original_trim` with score **0.937583**:

- Passing its record directly to `rejudge.one()` returns **zero**, without judging anything.
- Mapping the fields to the expected schema still makes the function locate the **untrimmed** reconstruction.

Thus the proposed independent check cannot currently validate the approximately +0.005 trim gain.

The analysis path also needs an explicit held-out configuration: [v2_dev.py still hard-codes the 60-part development manifest](/Users/Andrewlin/CADFit/bench/analysis/v2_dev.py:28). Its missing-record handling would silently turn fresh2 inputs into zeros if this driver were reused unchanged.

**Minimum fix before launch:** preserve and consume the selected program/tessellation path for trim results. Independently rejudge that selected artifact, without reselection, for each run before averaging. Ensure surface scoring also uses the selected trim output when reporting that arm. Supply an analysis invocation that explicitly reads the **fresh2 manifest** and checks all 300 records.

Smoke-test the revised path on existing development outputs with both a selected trim and a retained original. This requires no new search experiment.

**2. The source freeze still leaves the runner live, and d0 does not receive the promised sampling control.**

The complete archives fix the earlier missing-module problem. However, [arms_job.sh](/Users/Andrewlin/CADFit/bench/arms_job.sh:29) changes into the live checkout and executes:

```bash
bash bench/run_parallel_arms.sh ...
```

That live file supplies arm flags and environment settings when the queued job starts. Archiving it does not freeze execution if the job subsequently calls the checkout copy.

Separately, d0 is archived from `e260397`; its infrastructure patch does not contain the new revolve-seeding change. I checked the actual old function: repeated calls with `CADFIT_SEED=0` produce different samples, while the current function produces identical samples. Calling every arm “SEED 0” therefore overstates the matching.

**Minimum fix before launch:**

- Make jobs execute the runner from the frozen `h2_src` tree.
- Apply the same small revolve-seeding change to d0 as a common experimental-control patch, and describe it alongside the existing infrastructure patch.
- Define C as the final amended commit.

I am not asking for new snapshot machinery or a baseline redesign.

**3. The prespecified statistical family is internally inconsistent.**

The [protocol](/Users/Andrewlin/CADFit/review-stage/HELDOUT_PROTOCOL.md:59) specifies three incremental secondary contrasts plus **each arm versus section-only**, then says Holm correction covers **four** secondary contrasts. With five reconstruction configurations, that is eight contrasts.

The asymmetric repeat allocation is statistically usable: averaging three v2 runs against one dx run does not create a best-of advantage. But it is not a fully replicated, matched-seed v2−dx experiment, as the rationale currently suggests.

**Minimum fix before launch:** enumerate the family explicitly. My recommendation is four confirmatory secondary contrasts:

1. v2−dx.
2. v3−v2.
3. trim−v3.
4. Final trimmed method−section-only.

Report the other section comparisons descriptively. Keep the stated distinction between nominal mean-difference intervals and Holm-adjusted sign tests.

Also state that d0/dx results are single-run references. I would **not require additional d0/dx runs as a launch condition**. For repeated arms, distinguish per-run validity rates from the stricter “valid in every repeat” count produced by `--avg`.

**4. The new agent control substantially narrows the agent claim.**

Recomputed from [the first corrected Gemma repeat](/Users/Andrewlin/CADFit/results/devag_v2_r1_scores.json):

| Condition | Gated CAD IoU |
|---|---:|
| Code | 0.63358 |
| Code + section extrusion | 0.85763 |
| Full skills | 0.85824 |
| Matched scripted policy | 0.84879 |

The paired differences are:

- **Code+section−code:** +0.22405, nominal CI **[+0.11732, +0.33896]**.
- **Skills−code+section:** +0.00061, **[−0.02035, +0.02176]**.
- **Skills−policy:** +0.00945, **[−0.02195, +0.04135]**.

This repeat supports a large benefit from the section-extrusion tool. It does **not** demonstrate additional quality from the broader skills package or superiority of the learned controller.

**Minimum fix for the paper:** finish the remaining repeats and report these attribution contrasts prominently. Do not bury code+section in an appendix while presenting the full skill package as the established explanation. Absence of a significant difference is not equivalence.

This does not block the frozen pipeline launch.

**5. Surface fidelity, efficiency, and competitive novelty remain unestablished.**

The main surface defect is corrected. In the revised file, **293 of 294 valid reconstructions** use fused boundaries; one dx result uses the winding fallback. That fallback is an approximation, so it should remain explicitly identified rather than described as an exact occupied-boundary reconstruction.

On the 54 commonly valid parts, the corrected surface results still do not establish improved fidelity or preservation within a specified margin. Dev7 surface scoring is pending. Treat this as a diagnostic outcome, not an already-supported contribution.

Timing also requires less optimistic framing:

- v3 mean runtime is **554–620 seconds**, versus **460–540 seconds** for v2 across the three runs.
- Trim’s mean added stage time is **193, 338, and 197 seconds** across seeds.
- The largest recorded trim stage takes **3,188 seconds—about 53 minutes**.

The median trim is much cheaper, but it cannot stand in for expected cost. Furthermore, [dev7_durations.json](/Users/Andrewlin/CADFit/results/dev7_durations.json) contains anonymous lists, not records keyed by part. Those lists support aggregate summaries, but not independently checkable paired quality/time analysis.

Finally, the CADFather comparison remains pending, and the manuscript still describes the earlier experiment. The current work has promising engineering and empirical findings; its top-venue contribution is not yet established by the available comparison evidence.

**Minimum fixes for the paper:** finish the diagnostic surface evaluation, identify approximate/failing measurements, export timings keyed by part and run, and distinguish final-attempt latency from retry cost. Complete the common-judge CADFather comparison and rebuild the manuscript around the final results. No additional method optimization is necessary before held-out evaluation.

**Exact launch decision**

**May the supplied protocol and script launch as is? No.**

**Conditional go:** launch the pipeline study after implementing findings 1–3 and recording these final clarifications:

- Freeze the later agent/CADFather evaluation subsets—or an explicit outcome-blind sampling rule—before inspecting fresh2 pipeline outcomes. The current document is a pipeline protocol, not yet a complete full-scope study protocol. GPU execution can wait.
- Reconcile the node exclusions: the document excludes `1700–1709`, while the script leaves `1706–1707` eligible. Use the actual known-bad-node list consistently.
- State the commands/source tree used for scoring, trim, surface analysis, and final statistics. The script currently submits generation jobs only; its referenced postprocessing helpers do not constitute a supplied held-out analysis procedure.
- Retain part identifiers and retry information in the exported timing records. Reporting successful-attempt deployment latency is acceptable when labeled; it is not total computational cost.

These are bounded execution and protocol amendments. **Do not wait for Gemma repeats, CADFather completion, or dev7 surface scores merely to start the frozen CPU pipeline experiment. Do not add more method variants.**

The proposed arm matrix—d0, dx, v2, corrected v3, derived trim, and section-only—is appropriate.

The central paper claim should remain **reliable executable delivery**, now supplemented by evidence that extent corrections improve gated IoU and trimming offers a further quality/runtime tradeoff. About **54% of the development v3 gain comes from `00247424` alone**, so the untouched cohort is essential for assessing generality.

The agent contribution should be framed as an attribution study: substantial gains from geometric tools, with the first corrected repeat indicating that section extrusion explains nearly all of the observed quality gain.

## Memory Update

- Reviewed HEAD `6839f03`; recalculated dev7, trim, surface, timing, and first-repeat agent summaries. Full dev7 programs/trajectories were unavailable locally.
- Confirmed fixed: snapped-interval persistence through candidate generation; fused-boundary treatment of the saved compound; stacked-box representation invariance; current revolve seeding; complete archives for every requested arm; within-part repeat averaging.
- Dev7 three-run means: v2 **0.95172**, v3 **0.96045**, trim **0.96549**. All 360 v2/v3 deliveries valid. v3−v2 **+0.00873 [0.00188, 0.01971]**; trim **+0.00504 [0.00266, 0.00784]**, nominal development intervals.
- Confirmed rejudge integration defect: raw trim records return zero; field mapping alone still resolves the untrimmed STL. Selected trim artifact paths must reach independent judging and surface evaluation.
- Remaining freeze mismatch: queued jobs execute the live `run_parallel_arms.sh`. Remaining seed mismatch: d0’s archived revolve sampler ignores `CADFIT_SEED`.
- Existing analysis driver still hard-codes the development manifest. Held-out analysis must explicitly use fresh2.
- Protocol’s secondary family says four contrasts but lists eight. Recommended four: three incremental contrasts plus final method versus section-only.
- Gemma repeat 1: code **0.63358**, codesec **0.85763**, skills **0.85824**, policy **0.84879**. No demonstrated skills-over-codesec or agent-over-policy advantage.
- Surface main path is substantially repaired; one valid dx result still uses approximate winding fallback. Dev7 surface results remain pending.
- Trim runtime has substantial tails: seed means **193/338/197 seconds**, maximum **3,188 seconds**. Duration exports lack part identifiers.
- Conditional approval for held-out pipeline generation after the bounded launch/analysis amendments. No further method-development round is needed; pending GPU studies need not block CPU generation once their subsets are reserved.



## run_20261105_105505a5 Round 1 — Score: 5/10

### Raw Reviewer Response (verbatim)

Score: 5/10
Verdict: not ready

**The rescoring is defensible in principle, but the amendment needs tightening. The closed-model study is worth reporting as exploratory evidence, but its current endpoint does not consistently measure the delivered program. I also found a consequential trim failure outside the three flagged score files.**

I read the supplied diff, implementation, manuscript sections, all eight 300-part score files, both trim files, and all **195 episode records**, including the discarded Opus run. I independently checked aggregates and ran isolated code-path probes. The bundle contains no delivered agent programs, transcripts, or scheduler logs, so it cannot establish actual program validity or independently prove the attributed machine failures.

Remaining weaknesses, ranked by severity:

**1. The rescoring amendment conflates infrastructure failure with computational difficulty and does not enforce its stopping rule.**

The raw files confirm the stated counts:

| Run | Replay errors eligible under the amendment |
|---|---:|
| h2s0_dx | 299 sandbox setup failures |
| h2s2_v2 | 222 timeouts |
| h2s0_d0 | 7 SIGKILL exits and 3 timeouts |

Correcting the sandbox failures is legitimate: those programs never received a usable evaluation. But **SIGKILL does not establish external machine failure, and a timeout does not establish contention**. A program can exhaust memory or require excessive execution time. Successful sibling seeds are suggestive, not conclusive, because they can produce different programs.

The implementation is broader than the prose. [env_failure()](/Users/Andrewlin/CADFit/bench/score.py:195) accepts any error beginning with `timeout`, not specifically the documented 900-second case. More importantly, neither replay failures nor their scores are cached. My isolated probe called the actual scoring function three times with a repeated timeout: it recomputed three times and stored no terminal result. Thus **“a part that times out again is scored 0” is not enforced across subsequent resumptions**.

Applying a rule identically to all eight runs is necessary, but does not make a decision taken after outcomes existed prospectively preregistered.

**Minimum fix:**

- Describe this as a **post-outcome measurement amendment to frozen generation**, preserving its date and rationale.
- Separate confirmed setup/preemption failures from ambiguous timeout/SIGKILL failures. Without diagnostic logs, call the latter *resource-limit failures eligible for one recovery evaluation*, not proven machine faults.
- Freeze the eligible list from the original files and allow **one recovery scoring pass** under fixed resources, concurrency and the existing 900-second limit. Record the scorer’s existing internal retries too.
- Make the recovery outcome terminal. Another timeout, kill or setup failure remains zero in the declared operational metric, with its cause reported separately from geometric invalidity.
- Preserve original and recovery records and report how the primary and secondary estimates change. Do not choose between analyses according to significance.
- Do not regenerate programs or redo search/selection under this measurement amendment.

This preserves a credible held-out experiment. It does **not** justify describing the eventual analysis as an unchanged preregistration. A new cohort is not automatically necessary.

**2. The agent endpoint confuses “no completed verification” with “invalid delivered CAD.”**

The agent does use the corrected `robust_iou` inside its harness. That earlier concern is resolved. The remaining problem is when verification never returns.

[The execution path](/Users/Andrewlin/CADFit/agent/cad_tools.py:261) completes replay and scoring before updating `best_exec`. [Export](/Users/Andrewlin/CADFit/agent/cad_tools.py:504) falls back to the mesh-selected program when no executed incumbent exists. Consequently, `best_exec_valid = false` can describe **missing verification**, while a nonempty program is nevertheless delivered.

For **00560247 and 00928992**, all four retained agent conditions have:

- `best_exec_iou = -1`;
- a delivered STL path and one-step answer;
- approximately 1,801 seconds elapsed;
- almost all time spent in tools.

These records do not prove OCC-invalid geometry. They establish failure to obtain a verified answer within the episode. Several are labelled `stop: budget` despite using far fewer than 40 calls, because the loop also exits on elapsed time without changing the default stop label.

This distinction materially affects the comparison: those two zeros contribute **−0.04699** to Opus-code minus v3, whereas its overall difference is only **−0.02112**.

**Minimum fix:** independently replay and score **every retained delivered program**, under the same final evaluation settings as pipeline programs. Freeze the delivered answers; allow no further agent decisions. Report separately:

1. Final delivered-program validity and gated IoU.
2. Whether the agent completed verification within its episode budget.
3. No output, execution timeout, invalid geometry, and judge failure.

Keep both parts in every denominator. Missing programs remain zero. Successful offline evaluation is measurement of an already-delivered answer, not permission to continue the episode.

There are two concrete traps in the proposed rescoring route:

- [agentsk_score.py](/Users/Andrewlin/CADFit/bench/agentsk_score.py:100) still samples 20 parts using seed 1. On fresh2, **only two overlap the reserved 40**; it would omit 38 intended parts.
- Positional `score.py target.stl agent_model.stl --cad` **does not replay CAD**: [that CLI branch](/Users/Andrewlin/CADFit/bench/score.py:417) calls only the mesh judge. I verified the routing with a mocked judge.

Use the existing CAD scoring functions, but wire them explicitly to the reserved 40-part manifest and all four conditions. Merely adding `--cad` to the positional command is insufficient.

**3. The trim experiment contains a replay failure and an additional repair intervention.**

Two raw records contradict a clean “same delivery, plus silhouette trim” interpretation.

- **Seed 0, 00403399:** the pipeline score records valid CAD at **0.930698**. [The trim record](/Users/Andrewlin/CADFit/results/review_bundle_2026-11-05/h2s0_v3_trim.json:4714) records `timeout 600s`, no selected program, and zero. Its top-level status is nevertheless `ok`, so [trim_posthoc.py](/Users/Andrewlin/CADFit/bench/analysis/trim_posthoc.py:33) caches it.
- **Seed 2, 00057691:** the pipeline delivery is invalid and scores zero. [The trim record](/Users/Andrewlin/CADFit/results/review_bundle_2026-11-05/h2s2_v3_trim.json:589) reaches **0.883024 before trimming**, then **0.906910 after trimming**. Most of that part’s improvement comes from another fusion/repair pass.

Across 300 parts, seed 2’s final-package increment is **+0.01258**, while its within-pass trim increment is **+0.00964**. These are different quantities.

The code explains why: [verify()](/Users/Andrewlin/CADFit/exec_verify.py:248) reruns original/fused candidates and repairs invalid outputs before constructing the trimmed candidate. Its trim timer starts only afterward, so it excludes this additional work.

**Minimum fix:** retain the preregistered final-package-versus-v3 contrast, but describe the implemented package accurately. Add a diagnostic decomposition using `gated_no_trim`, and retain the corresponding artifacts for independent checking. Report the complete added wall time if claiming the cost of this postprocessing package.

For 00403399, retain the frozen failure unless a documented amendment justifies recovery. **Do not silently use the scoring amendment to rerun candidate selection.** Retaining the previously verified original is the appropriate delivery fix, but introducing that behavior now is a disclosed post-outcome method correction.

**4. The closed-model results support a useful descriptive study, not a robust ranking or equivalence claim.**

The cohort selection is correct: I reproduced the seeded 20+20 draw, and every retained condition covers exactly those 40 parts. The exported aggregate arithmetic also matches the raw records.

Current **harness-based**, validity-gated results are:

| Condition | Mean IoU | Verified answers |
|---|---:|---:|
| Sonnet code | 0.89965 | 38/40 |
| Sonnet skills | 0.88431 | 37/40 |
| Opus code | 0.93012 | 38/40 |
| Opus skills | 0.88517 | 36/40 |
| Pipeline v3, three-run average | 0.95124 | — |

My paired, split-stratified bootstrap gives nominal 95% intervals:

- Sonnet skills − code: **−0.01534 [−0.07117, +0.01819]**.
- Opus skills − code: **−0.04495 [−0.12003, +0.00999]**.
- Opus code − v3: **−0.02112 [−0.09877, +0.03642]**.

Neither tools comparison establishes a mean improvement or deterioration. Opus versus v3 establishes neither superiority nor equivalence.

Moreover, Opus skills’ two additional failed deliveries, **00300195 and 00867782**, contribute **−0.04851** to its mean difference from code—more than the entire observed deficit. The remaining parts contribute **+0.00356**. Sonnet shows the same qualitative pattern with one additional failure. That makes this an interesting **tool-cost and delivery-reliability finding**, not evidence that stronger models generally reason worse with CAD tools.

**Minimum fix depends on the claim:**

- **Exploratory paper subsection:** one episode per cell is reportable after common final scoring, with paired intervals, failure decomposition and explicit limits.
- **Central model/tool comparison:** add two independent episodes per condition on the same 40 parts, giving three total. Average within part and bootstrap parts within split. Three is a practical minimum for assessing repeatability, not a guarantee of adequate precision.
- **Planning or tool-attribution claim:** complete the already-planned code+section and matched-policy controls. A code-versus-skills package comparison cannot isolate planning.

Do not treat the contaminated d0/dx/v2 rows as comparative evidence. The two-seed trim result is also provisional, not the planned three-seed endpoint.

**5. The discarded run and figure need auditable reporting.**

The discarded Opus directory contains **17 code and 18 skills episodes**, all without a verified answer. That strongly suggests a systematic problem, but `result.json` does not substantiate the claimed per-call 90-second failure mechanism. The discarded records contain **$8.9535 in estimated API cost**, excluded from the displayed retained-run costs.

Setting aside a demonstrably broken machine run is reasonable. **Minimum fix:** supply its tool-error transcripts/job diagnosis, disclose the whole discarded block and its cost, and state the replacement rule. The new [preflight](/Users/Andrewlin/CADFit/bench/claude_job.sh:27) should exercise the actual sandboxed replay/tessellation path; an unsandboxed box-volume calculation does not test the failure path that affected scoring.

Two smaller, confirmed reporting defects:

- [make_closed.py](/Users/Andrewlin/CADFit/bench/figures/v2_2026-10-23/make_closed.py:25) hard-codes **mesh `best_iou` gated by executed validity**, whereas the analysis uses `best_exec_iou`. The discrepancy is small here, but it is the wrong metric for this paper. Generate the figure from final scoring records and include uncertainty.
- [AnthropicChat](/Users/Andrewlin/CADFit/agent/anthropic_chat.py:31) uses **32,000 tokens per turn**, ignoring the caller’s `max_tokens`, and preserves full native history. Report those actual settings. They are consistent across the two closed models, but differ from the open-model harness settings.

**6. The manuscript still describes the superseded experiment, and the decisive evidence is unfinished.**

[The setting section](/Users/Andrewlin/CADFit/paper/sections/3_setting.tex:21) still describes 60 fresh parts and single-run arms; the agent section describes the historical 20-part study; [numbers.tex](/Users/Andrewlin/CADFit/paper/numbers.tex:460) still contains `PENDING`. The old “never inspected during development” framing cannot describe a cohort subsequently used throughout these repairs.

The launch-related fixes are visible and appropriate: frozen runner routing, d0’s seeding patch, explicit secondary contrasts, and selected trim artifact routing. I would not reopen those resolved objections.

**Minimum fix:** finish the corrected held-out scores, third trim run, section control, independent rejudging, surface diagnostics, timing and declared statistics. Rebuild the manuscript around those results, identifying the older cohorts as development/history. Complete the planned common-judge CADFather and corrected agent controls if retaining competitive or planning claims; otherwise narrow those claims.

For a top venue, the strongest prospective contribution remains **a reproducible diagnosis and repair of executable-delivery failures, with controlled evidence about geometric tools**. The supplied artifacts do not yet establish that contribution at submission standard.

## Memory update

- Reviewed HEAD `3eab8d19`; inspected the full supplied diff, eight 300-part score files, two trim files and 195 episode records. Programs, transcripts and scheduler evidence remain unavailable locally.
- Confirmed 531 replay records match the amendment’s eligibility rule. Recovery is defensible, but timeout/SIGKILL attribution is unproven and terminal retry handling is absent.
- Agent `best_exec_iou = -1` means no completed executed incumbent, not proven invalid delivered geometry. Independently score all delivered programs; retain online verification success separately.
- New scoring integration defects: `agentsk_score.py` selects the wrong 20 parts—only two overlap the reserved 40—and positional `score.py --cad` ignores CAD replay.
- New trim findings: seed-0 `00403399` loses valid 0.930698 to a cached 600-second replay timeout; seed-2 `00057691` gains 0.883024 through repeat fusion/repair before trimming.
- Closed-model means verified; paired tools-versus-code and Opus-code-versus-v3 intervals include zero. Extra failed deliveries explain the skills mean deficits.
- Next review needs terminal recovery records, common final agent scores, complete three-seed trim/statistics, failure evidence and a manuscript reflecting the actual study.


---


## run_20261105_105505a5 Round 2 — Score: 6/10

### Raw Reviewer Response (verbatim)

Score: 6/10
Verdict: not ready

The closed-model study is now credible **exploratory evidence**, and materially stronger than last round. Three repeats, common offline CAD replay, complete denominators, and averaging repeats within parts are the right corrections. I give no credit for the still-uncomputed preregistered contrasts, and draw no negative conclusion about their eventual outcomes.

I independently recomputed the principal means and paired bootstrap intervals from the three score files, and checked the 480 retained episode records.

| Condition | Mean validity-gated CAD IoU | Valid deliveries |
|---|---:|---:|
| Opus / code | 0.97488 | 120/120 |
| Opus / skills | 0.94109 | 115/120 |
| Sonnet / code | 0.94552 | 120/120 |
| Sonnet / skills | 0.93226 | 117/120 |

The corresponding pipeline references are **0.95124 for v3** and **0.95971 for the two available trim seeds**. The new primary figure uses the correct endpoint and excludes the contaminated d0/dx/v2 references. That is correct.

The remaining weaknesses, ranked by severity:

**1. The contribution must accommodate the strong code baseline; the existing manuscript does not yet do so.**

Opus/code exceeds v3 by **0.02364**, with a nominal paired 95% interval **[0.00293, 0.04777]**. But its difference from the available trim reference is **0.01517 [−0.00136, 0.03245]**. Thus “Opus code beats v3 on this exploratory comparison” is supported; superiority over the final pipeline package is not established. These intervals also come from an analysis reporting twelve exploratory comparisons, not a prespecified superiority test.

For skills minus code:

- Opus: **−0.03379 [−0.09696, 0.00931]**.
- Sonnet: **−0.01326 [−0.06832, 0.01983]**.

Both aggregate means are lower, but neither interval establishes a negative population effect. Nor do these results establish equivalence. Skills actually wins on **26/40 parts for Opus** and **21/40 for Sonnet** after averaging repeats. The aggregate result includes a consequential failure tail.

The honest contribution is an **execution-based audit of reconstruction quality and tool use**, including the finding that these additional CADFit tools do not demonstrate an aggregate quality benefit for the tested closed models under this budget. The current paper title already supports that framing.

**Minimum fix:** narrow the claims explicitly:

- Do not claim that CADFit-specific tools generally improve strong agents, that the pipeline is the strongest reconstruction method, or that LLM planning adds value without the matched policy result.
- Preserve the historical open-model findings with their actual cohort and harness qualifications. The closed-model result does not falsify those narrower findings.
- Do not infer “tools help weak models but not strong models” as a controlled interaction: the historical and current studies differ in cohort and harness, including the documented 32,000-token/full-history Claude configuration.
- Describe “code” accurately: it already includes geometric observations, execution and feedback. This is not an unaided language-model baseline.

Three episodes per condition are enough to report this exploratory study. More repeats are not automatically required to rescue an unfavorable tools result.

**2. The recovery amendment is defensible, but its claimed execution as one symmetric pass remains unverified.**

The rewritten [amendment](/Users/Andrewlin/CADFit/review-stage/HELDOUT_PROTOCOL.md:94) correctly distinguishes sandbox setup failure from resource-limit failure, explicitly acknowledges its post-outcome timing, freezes generation, makes repeated failures terminal, and commits to reporting original and recovered analyses. Current [scoring code](/Users/Andrewlin/CADFit/bench/score.py:195) caches failures, and the clearing script refuses a second clearance. These are substantive fixes.

I also verified that all eight files in `results/heldout_pre_recovery/` match the original review-bundle records. They contain **299 setup failures, 222 v2 resource failures, and 10 d0 resource failures** eligible under the rule.

The remaining problem is the [execution log](/Users/Andrewlin/CADFit/review-stage/HELDOUT_PROTOCOL.md:120): d0’s unsuccessful recovery is terminal, while dx was cancelled and resumed under code that did not cache failures. “Cancelled before writing its score file” does **not** establish that no failed evaluations had already completed.

**Minimum fix:** reconcile dx’s actual attempts from job output and per-part records. Distinguish completed evaluations from interrupted or unstarted evaluations. Under the declared rule, a completed failed recovery is terminal; merely restarting the aggregate job must not erase that outcome. If another node-fault exception was necessary, document it as another amendment, apply its eligibility criteria consistently, and retain the first-pass sensitivity analysis.

This need not invalidate the experiment. But the recovered analysis is **post-outcome amended**, while its hypotheses and contrasts can remain prespecified. Calling the entire recovered analysis unchanged preregistered evidence would be inaccurate.

**3. The paper’s central confirmatory evidence and manuscript are still unfinished.**

The required pipeline contrasts do not exist yet. The manuscript still describes the earlier 60-part/20-part studies, and [numbers.tex](/Users/Andrewlin/CADFit/paper/numbers.tex:400) contains substantial `PENDING` content. The protocol’s closed-model paragraph also still says one episode.

**Minimum fix:** finish the already-planned recovery, third trim seed, controls, rejudging, surface diagnostics, timing and statistics; then rebuild the manuscript around the actual results. Report the original and amended recovery analyses together.

The trim qualification remains necessary: distinguish the complete final-processing package from trim proper using `gated_no_trim`, and include the full added processing time. Do not attribute gains from another fuse/repair pass solely to silhouette trimming.

This is a submission blocker, not evidence that the pending contrasts will fail.

**4. The failure descriptions are more confident than the supplied evidence permits.**

All **472 delivered outputs** in the retained closed-model score records are valid. The eight failures are **no-output episodes at approximately 1,800 seconds**, concentrated on three parts:

- `00867782`: all six skills episodes.
- `00300195`: one Opus skills episode.
- `00928992`: one Opus skills episode.

They are not eight delivered programs found geometrically invalid. The earlier “every agent invalid” interpretation of `00560247` and `00928992` must be withdrawn; neither part should be excluded.

The episode records establish deadline exhaustion without output. The aggregate per-tool file does not identify the responsible call in each failed episode, so it cannot by itself prove that *every* failure arose from one specific long call.

Similarly, the discarded-run [diagnosis](/Users/Andrewlin/CADFit/results/review_bundle_2026-11-05/agentsk_f2/opus55_node4002_failed/diagnosis.json) contains timeout counts, not the underlying tool errors or scheduler evidence establishing a node fault. The new sandboxed box preflight is appropriate prevention, but is not retrospective proof.

**Minimum fix:** include the relevant raw failure traces and historical job/node evidence supporting the exclusion and causal descriptions. Keep deadline failures in the primary denominator as zero. Report discarded infrastructure expenditure separately from retained-episode cost.

**5. A secondary metric still combines scores from different candidate programs.**

[agentsk_score.py](/Users/Andrewlin/CADFit/bench/agentsk_score.py:123) copies `best_iou` into `agent_iou`; [closed_vs_pipeline.py](/Users/Andrewlin/CADFit/bench/analysis/closed_vs_pipeline.py:65) gates that value using `best_exec_valid` and labels the result `[harness]`.

That combines the best **mesh** score with the validity of the best **executed** program. The mismatch actually occurs: Opus/code repeat 1, part `00562295`, has mesh-best **0.92689** but executed-best **0.66130**.

**Minimum fix:** carry `best_exec_iou` explicitly and use it for the executed harness diagnostic, or label the mesh diagnostic accurately. Regenerate those secondary rows. **The primary offline scores and new figure are unaffected.**

**My ruling on the proposed tool-improvement study: proceed, with a more precise claim and controls.**

Developing on development parts, freezing the implementation, and running old and new versions on the same prospectively selected cohort is sound. An improved release is not a prerequisite for publishing the current negative result.

The minimum adjustments are:

1. **Be precise about the new cohort.** The other 260 fresh2 parts are agent-unseen, but their pipeline outcomes have already been available and inspected. They can support a prospectively specified, exploratory agent follow-up. They should not be described as wholly untouched held-out data. For that stronger claim, draw outside all 300 fresh2 parts and previous development/evaluation sets, preserving source-part disjointness.

2. **Match the controls to the claim.** Old versus new skills is sufficient to test whether the tool package improves. To claim that CADFit skills add value beyond code, the code condition must receive the same cheaper checking, caps and caching. An old/new × code/skills comparison separates these effects. Keep three episodes per part, average within part, and predeclare the primary comparison, failure treatment and stopping policy. Interleave conditions under comparable resources.

3. **Cheaper checking is reasonable, but changing sample count alone may miss the bottleneck.** [robust_iou](/Users/Andrewlin/CADFit/bench/score.py:106) first attempts exact geometry, then samples toward a minimum union count. Reducing `n` does not reduce exact-boolean work and may simply cause more sampling batches. Profile replay, validity, tessellation and judging separately on development parts; choose the approximation there. Keep the final common judge unchanged.

4. **A call cap needs a defined answer-selection rule.** Keeping a step as unchecked is reasonable when its construction succeeded but scoring did not finish. Distinguish that from a step never successfully executed. Preserve the previous verified candidate, communicate uncertainty explicitly, and freeze how checked and unchecked candidates compete for delivery. Offline scoring must evaluate the one delivered answer, not select retrospectively among checkpoints.

5. **Replay memoization already exists.** [CadWorkspace._exec](/Users/Andrewlin/CADFit/agent/cad_tools.py:261) caches by program text, but installs its record after robust judging and manifold preparation. Interrupted judging can therefore lose reusable completed replay work. The concrete improvement is to retain successful replay results separately from unfinished quality checking—not to assume the system currently has no cache.

6. **Do not commit to mesh decimation before profiling `extract_sketch`.** It slices, densifies loops to roughly 3,000 points or more, and fits primitives for all profiles before limiting the displayed results. See [extract_sketch](/Users/Andrewlin/CADFit/agent/skills.py:242). Decimation may not address the expensive stage. Measure slicing versus profile fitting first; validate any approximation on development geometry and retain the original target for final judging.

One numerical correction to the optimization rationale: `add_code` accounts for **84–89% of code-arm tool time**, but approximately **68–71% of total episode wall time**. The tool-time totals reconcile with the episode records to rounding precision.

## Memory update

- Round 2: **6/10; not ready**. Closed-model evidence improved substantially; pending pipeline contrasts remain unassessed.
- Verified 480 retained episodes and three common-judge score files. Code arms each deliver 120/120 valid programs; skills deliver 115/120 and 117/120.
- Opus/code exceeds v3 in the exploratory paired interval; superiority over the available trim reference is unresolved. Skills-minus-code intervals include zero for both models.
- Eight skills failures are deadline/no-output cases on three parts; all 472 delivered outputs are valid.
- Recovery rule now handles terminal failures appropriately, but dx’s cancelled/resumed pass needs per-part reconciliation.
- Remaining concrete bug: `[harness]` rows gate mesh-best IoU using executed-best validity. Primary offline results are unaffected.
- New optimization study is reasonable with development-only tuning, fixed delivery rules, common final scoring and matched code controls. Remaining fresh2 parts are agent-unseen, not wholly untouched.
- Main blockers: completed held-out analyses, recovery audit, evidence for exclusions, and a manuscript whose claims match the corrected results.

---

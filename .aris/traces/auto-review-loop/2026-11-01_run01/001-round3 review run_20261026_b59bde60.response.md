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
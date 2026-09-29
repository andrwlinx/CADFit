### Dev (60 = 30 benchA-hard + 30 benchE-hard)

Strict IoU, paired against `base` (the phase-2 HEAD defaults). 95% bootstrap CIs. "±" counts are parts that changed by more than 0.005.

| arm | benchA | benchE | all 60 | Δ vs base (95% CI) | better/worse | wall time |
|---|---|---|---|---|---|---|
| base | 0.906 | 0.795 | 0.851 | – | – | 414 min |
| rules | 0.907 | 0.822 | **0.864** | +0.014 [+0.003, +0.025] | 26/3 | 267 min |
| all (rules + loft/sweep) | 0.905 | 0.822 | 0.863 | +0.013 [+0.002, +0.025] | 26/3 | 344 min |
| rules + refinement fixes (§5.3) | 0.901 | 0.821 | 0.861 | +0.010 [−0.003, +0.023] | 25/5 | 281 min |

- **benchE-hard is a clear win:** +0.026 to +0.028 across all rule arms; the CI excludes 0.
- **benchA-hard is flat.**
- **Loft/sweep is neutral on CADBench:** 6 parts better and 4 worse than `rules`. That is consistent with §2: 0.3% of benchA surface area is freeform.
- **The refinement fixes are robustness fixes;** their effect is within noise (3 parts better, 2 worse than the first `rules` run).
- **Multi-start greedy** (`--multistart`: forward orders ratio/IoU/volume, plus the pool without loft/sweep) fixed none of the regressions on a 5-part check. It stays in as an off-by-default flag.

**Why benchA stays flat: the search is path-dependent.** On 00112116, `rules` reached 0.956 only because its greedy result was poor (0.688). That triggered the single-candidate fallback (0.746), and the residual refinement pass then carved it up to 0.963. With lofts, greedy reached a genuinely better 0.84, and refinement had less to fix: final 0.850. A worse start can end better and a better start can get stuck. So the next lever is the composition search itself (beam search on exact IoU), not more candidate types.

### Frozen test (100 × benchA-hard)

_pending_: base vs rules.

### 5.3 Post-greedy fixes (found while investigating benchA regressions)

1. **Exact-union exports crack on the STL round trip.** Float32 rounding plus lost vertex indexing make trimesh see a non-watertight, multi-body mesh. Re-measuring then alpha-wrapped it: 0.756 against a true 0.840. Fix: `iou._merged_manifold` rebuilds the manifold directly with `Mesh.merge()`, accepted only with a clean status and matching volume.
2. **Refinement silently skipped** ("Could not compute over-reconstruction"), because trimesh booleans refuse such meshes. Fix: the residuals (recon − GT, GT − recon) now use manifold3d under `--exact-union`.
3. **The refinement combine timed out** (OCC cut on a compound holding lofts took more than 300 s). Fix: the refined mesh is the exact manifold cut/union of the two STLs. The combined CadQuery script is still written as the CAD program.
4. Loft/sweep solids are no longer used as cut-phase tools.

# CADFit++ Phase 3: real benchmarks, better rules, loft and sweep

Status: in progress (dev runs going). Sections marked _pending_ are waiting on runs.

## 1. Data

**CADBench** is `DeCoDELab/CADBench` on Hugging Face, from the same MIT DeCoDE lab as CADFit (arXiv 2605.10873). "Bench A (hard)" is the `benchA` split with `label == 'hard'`: 1,000 ABC shapes with 138–12,292 B-rep faces, chosen for operation variety. The paper reports stock CADFit at IoU **0.832** / CD 0.039 on benchA-High from clean meshes.

**File-name trap:** split names and file prefixes are swapped. `benchA` lives in `data/bench1B-*` and `benchE` in `data/bench1A-*`. `bench/fetch_cadbench.py` indexes labels by split name and downloads only the row groups it needs, as STL + STEP. Sets, seeded and non-overlapping:

| set | contents | use |
|---|---|---|
| smoke | 5 × benchA-hard | crash and timing checks |
| dev | 30 × benchA-hard + 30 × benchE-hard | every arm comparison |
| test | 100 × benchA-hard | frozen; milestone runs only |

The ABC raw chunks (`fetch_abc.py` in the plan) were not needed. CADBench's A and E tiers already are deduplicated, single-body, high-face-count ABC.

## 2. What benchA-hard is made of (`bench/gt_surface_stats.py`)

B-rep faces of 158 downloaded GT STEP files (dev + test), classified with OCP:

| surface type | mean area fraction |
|---|---|
| plane | 0.776 |
| cylinder | 0.185 |
| cone | 0.019 |
| torus | 0.012 |
| extrusion surface | 0.005 |
| bspline | 0.003 |

- **Planar area:** 83.2% has an axis-aligned normal, 15.8% is side walls of axis-aligned extrusions (normal perpendicular to X, Y or Z), and 0.9% is compound-angle. Only 6 of 158 parts have more than 10% compound-angle planar area.
- **Rotational surfaces** (cylinder, cone, torus): 2.2% of their area has a non-XYZ axis (10 of 139 parts).

**Consequence:** on this benchmark, oblique extrusion directions, oblique revolve axes, lofts and sweeps are rare. The error is mostly about covering many axis-aligned features, composing them correctly, and the metric that steers the search. Priorities were reordered accordingly (the plan's phase-A rule). Loft and sweep were still built, because ABC-style freeform parts and user meshes need them.

## 3. Findings about the stock search

1. **The greedy objective is biased.** Each forward/backward step concatenates the selected candidates' STLs. The overlapping compound fails the single-body check, so the whole model is alpha-wrapped before the IoU is taken. Alpha-wrap fills concave detail. On smoke part 00053793 the search believed 0.954 while the strict judge measured 0.982. The bias varies by candidate, so it also changes which candidates are accepted. The cost grows with model size on every step.
2. **About 90% of each CadQuery call is interpreter startup:** median 1.54 s, of which 1.37 s is `import cadquery`.
3. **A silent loss of slices.** `extract_sketches.py` and `extract_planar_contours.py` fall back to `entity.discrete()` when trimesh cannot build polygons. Current trimesh requires a `vertices` argument, so the call throws and the slice is dropped. This happened 7 times on 4 smoke parts.
4. **The pipeline reports success on failure.** A crash inside `greedy_search.py` still counts as a successful part in the final summary. Only the strict judge (`bench/score.py --runs`) catches it.
5. **Removed from the plan:** the suspected revolve-axis bug (`analyze_revolve_axis.py:296`) has no effect. Callers already pass the centroid, and downstream code uses `mean_point`.

## 4. Changes (all flag-gated; stock reproducible)

| flag | what it does | kind |
|---|---|---|
| `--persistent-cq` | Runs each generated script in a long-lived interpreter per worker (`cq_worker.py`), not a fresh `python`. Same scripts; byte-identical STLs. Timeouts and failures behave as in stock. | speed, lossless |
| `--exact-union` | Scores a composition as an exact manifold3d union of the cached per-candidate solids, not an alpha-wrapped concatenation. Unbiased and much faster. | speed + objective fix |
| `--fix-slice-fallback` (default on) | Passes vertices to `discrete()`, so fallback slices are no longer lost. | bug fix |
| `--seed N` (now covers everything) | `CADFIT_SEED` seeds planar-contour sampling and the >100-entry subsample, not just translation sampling. The analysis stage is byte-reproducible. | methodology |
| `--cut-phase` | After greedy add/prune, subtracts candidate solids while IoU improves. Every evaluated candidate is a possible tool, including the near-zero-IoU ones stock throws away (a hole's own extrusion is empty space). Cuts are emitted as `result = result.cut(...)`. | new rule |
| `--event-slices` | Slices midway between consecutive heights of axis-normal planar faces, so every 2.5D layer gets its own section however thin (evenly spaced slices skip thin layers; planar-contour slices sit 0.05 inside a face, which lands inside chamfers and bevels). | new rule |
| `--detect-directions` | Gauss-map extrusion directions: clusters face normals, takes cross products of cluster pairs as candidate directions, scores each by perpendicular wall area (at least 3 walls, no single dominant plane), and refines with the Point2Cyl eigenvector. Slices along directions not covered by X/Y/Z or planar caps. Oblique prism recovered within 0.012°. | new rule |
| `--translation-max-points N` | Uses a stride subsample of each loop in the translation chamfer sweep. Loops are densified to 3,000 points. | speed, lossy |
| `--sweep-loft` | Proposes loft and sweep candidates by tracking cross-sections (`analyze_sweep_loft.py`); they enter the search as self-describing "generic" ops. | new operations |
| `--emit-splines` | Emits fitted spline fragments instead of dropping them. Measured to be rare: any three points fit an arc. | completeness |

### Loft and sweep (`analyze_sweep_loft.py`)

Seeds are single-loop sketches. From each seed, a section plane marches through the mesh (step 0.04 in the [-1,1] frame), following the nearest outer loop. Tracking stops on an area jump beyond ×0.6 or ×1.6, or when the loop disappears. Ends are extended by bisection to where the section vanishes.

- **Straight tracking** (fixed normal): if the section changes (shape deviation or centroid drift above 3% of size), it becomes a **loft**. Sections are resampled to 48 arc-length points, start-aligned by cyclic shift, and keyframes are picked by adaptive subdivision until linear interpolation is within 0.01. CadQuery: `Solid.makeLoft` through periodic splines.
- **Bent tracking** (plane re-aimed at the next centroid): if the path turns more than 12°, it becomes a **sweep**. The profile is the median-area section, carried to the path start. The path is a moving-average-smoothed centroid path resampled by arc length. A loft through the tilted sections is also proposed, which covers profiles that change along a curved path.
- **Three failure modes found and fixed:**
  - Profiles rounded to 5 decimals are non-planar by about 1e-6, and OCC then returns an open *shell*. The profile is now emitted in exact plane coordinates.
  - End sections graze the caps and are clipped. The profile now comes from the median section.
  - A raw centroid path zigzags and self-intersects. It is now smoothed.
- Every generated solid asserts `isValid()`.

Single-candidate recovery on the new synthetic families (`bench/test_sweep_loft.py`, `bench/make_synthetic.py --p3`):

| part | best loft | best sweep |
|---|---|---|
| bent_pipe_0 | 0.987 | 0.974 |
| bent_pipe_1 (tilted) | 0.976 | 0.958 |
| loft_square_circle_0 | 0.983 | – |
| loft_square_circle_1 (tilted) | 0.989 | – |
| plate_with_loft_handle_1 (tilted) | 0.839 | – |
| s_swept_bar_1 (tilted) | 0.914 | – |

The swept S-bar with an untilted planar path is really an extrusion of its flat face, and the stock extruder covers it.

## 5. Results

### Smoke (5 × benchA-hard), frozen code per arm

Strict judge (`bench/score.py --runs`). Arms `speed`…`all` are the second run (`p3smoke2`), after the measurement fixes in §5.1. "4 common" means the parts shared with the phase-2 baseline run, which only had 4 inputs.

| arm | flags added | mean strict IoU (4 common) | mean CD | heatsink part (00965166) |
|---|---|---|---|---|
| base | phase-2 HEAD defaults | 0.9332 | 0.0141 | – |
| speed | `--persistent-cq --exact-union` | 0.9466 | 0.0125 | 0.817 |
| cut | `+ --cut-phase` | 0.9465 | 0.0125 | 0.817 |
| rules | `+ --event-slices --detect-directions --translation-max-points 400` | **0.9472** | **0.0124** | 0.966 |
| all | `+ --sweep-loft --emit-splines` | 0.9042 → **0.9472*** | | **0.983*** |

\* The `all` arm was re-run per part after the self-intersecting-loft filter and the multi-body fix (§5.1). The p3smoke2 `all` numbers predate both fixes.

**Timing** (sequential, no other load): `speed` did the 5 parts in 13.5 min. `base` did 4 parts in about 35 min, with 00053793 going from 904 s to 70 s and 00380269 from 624 s to 408 s. Part of the speedup comes from quality: with the unbiased objective, greedy clears the refinement thresholds more often, so the residual passes (up to 312 s of planar-contour extraction on part 3) run less.

The heatsink part shows how the rules combine. Event slices supply the fin-comb profile, the cut phase carves 9 fin gaps from the block, and a loft covers one sloped component: 0.817 → 0.966 → 0.983.

### 5.1 Measurement bugs found on the way (all fixed)

1. **Re-measure alpha-wraps valid multi-body results.** After greedy, stock re-measures the final STL. Any mesh with more than one body (a cut that splits a part, or disjoint unions) is alpha-wrapped, which fills fin gaps and pockets. The lower score then triggers the "best single candidate" fallback. On the heatsink this replaced a 0.978 composition with a 0.878 single extrusion. Fix: with exact-union on, each closed body is converted separately and the bodies are unioned exactly (`iou._bodies_union_manifold`).
2. **Self-intersecting lofts pass every cheap check.** A loft that twists through itself is watertight and consistently wound, and OCC `isValid()` accepts it, but opposite-orientation regions cancel in the volume integral. One such loft made greedy believe 0.998 on a part whose true score was 0.776. Fix: reject loft/sweep candidates whose alpha-wrapped volume exceeds 1.12× the mesh volume (15 of 85 rejected on 00399282). Exact-union and cut scoring also refuse inconsistent boolean volumes.
3. **An edit during a run leaked into it.** A mid-run edit to `cadquery_ops.py` crashed greedy on 3 parts, and the pipeline still reported "5/5 successful". Fix: `run_full_arms.sh` runs each arm from a frozen code snapshot, and only the strict judge is trusted.

### Dev (60) and frozen test (100)

_pending_

### 5.2 Robustness fixes found on the dev set (stock bugs too)

- **Slice blow-up on perforated sheets.** Dev part 00638515 is a thin sheet with about 780 holes. Every slice through it crosses hundreds of strips, and stock densifies each strip to 3,000 points. Even the baseline wrote 2.2 GB of sketch JSON (plus a 2.2 GB copy) and filled the disk. New option `--max-slice-loops` (default 200; `0` restores stock) skips such slices, bringing that file down to 84 MB. The sheet's outline still comes from the planar-contour sketch of its top face. Event slices are also capped at 6 extra per direction, and busy extra slices (more than 50 loops) are skipped.
- **pymeshlab alpha-wrap segfaults kill the pipeline.** On dev part 00787927 the final IoU check segfaulted inside `generate_alpha_wrap`, in the main `run_pipeline` process, in both `base` and `rules`. The wrap now runs in a persistent helper process (the `cq_worker.py` protocol). A crash there restarts the helper and falls back to the existing soft-failure path, so the part finishes (IoU 0.630). Output is identical (checked on a benchmark part); only the first call pays about 3 s of startup. Plain `fork()` does not work because macOS aborts forked children once the Objective-C runtime is up. `CADFIT_SAFE_WRAP=0` restores in-process wrapping.
- **The arm runner now runs one part per pipeline call,** stops below 3 GB free, and attempts each part once.

## 6. Failure cases seen

- **Beveled rim plate** (00380269): the planar-contour section sits inside the bevel, so the hexagon is too small and extruded at full thickness. Event slices supply the mid-plane section. A chamfer or loft is still needed for the rim.
- **Heatsink board** (00965166, 90k faces): dense thin fins get covered by one block, and the plate ends and side components are missed.

## 7. Reproduce

```
.venv/bin/python bench/fetch_cadbench.py --set smoke --set dev --set test
bench/run_full_arms.sh bench/cadbench/smoke p3smoke base speed cut rules all
.venv/bin/python bench/score.py --runs bench/runs/p3smoke_* --stl-dir bench/cadbench/smoke
.venv/bin/python bench/test_p3.py && .venv/bin/python bench/test_fixes.py
```

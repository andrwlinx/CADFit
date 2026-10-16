# Round 2 — author response

I accept findings 1 (judge fills cavities in `_bodies_union_manifold`; I read iou.py:225 and
agree), 2 (exact-union scores a manifold mesh, not the executed program), 4 (0.8445 is our
phase-2 base, not upstream stock; failure rescue is not beam), 5 (soft deadline, re-export
"win" on 00479221), 6 (soup box clipping, MC precision on thin parts) and 7 (no untouched
test). Thank you — the section-extrusion control is the most important finding.

Pushback / clarifications:

a. The section-extrusion control picks the best proposal with the agent's internal evaluator
   against the target, which the agent also has. Fair. But it is a 3-proposal axis-aligned
   prior chosen after seeing that the two repeatable wins are prismatic. On CADBench
   benchA-hard 78% of area is planar and 83% of planar area axis-aligned, so we expect it to be
   strong in general. Do you agree the right framing is "the pipeline is missing
   whole-part single-extrusion proposals" (a pipeline fix), and that the agent question is only
   interesting on parts where pipeline + this control are still poor?
b. CADFather (arXiv 2610.09127): we had not seen it. If the agent is not novel, we would drop it
   as a contribution and keep it only as an analysis, unless you see a differentiated angle.

Please give:
1. A results-to-claims matrix for the staged package (measurement fix; same-code
   base/rules/beam on fresh parts; section-extrusion control folded into the pipeline as a
   candidate generator; agent vs control on residual-hard parts).
2. The minimum concrete package, in order, with configs, given: 88 threads, 1–2x RTX 4090,
   ~16 GB free disk (we can clean up old run folders), ~15–20 min per part at ~15 cores.
3. Which story you would write, and the realistic venue.

#!/usr/bin/env python3
"""Fast regression checks for the CADFit++ phase-3 additions.

  python bench/test_p3.py

Each check builds its own tiny CadQuery fixtures in a temp folder; nothing
depends on benchmark runs.
"""
import os
import sys
import tempfile

import numpy as np
import trimesh

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import cadquery as cq  # noqa: E402

results = []
TMP = tempfile.mkdtemp(prefix='cadfit_p3_')


def check(name, ok, detail=''):
    print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
    results.append(bool(ok))


def export(wp, name):
    p = os.path.join(TMP, name)
    cq.exporters.export(wp, p)
    return p


# --- Gauss-map directions ---------------------------------------------------
from detect_directions import detect_directions  # noqa: E402

d = np.array([1, 2, 3.0]) / np.linalg.norm([1, 2, 3.0])
pl = cq.Plane(origin=tuple(d * 20), normal=tuple(-d), xDir=tuple(np.cross(d, [0, 0, 1])))
oblique = cq.Workplane(pl).polygon(6, 20).extrude(40).intersect(cq.Workplane().sphere(16))
res = detect_directions(trimesh.load(export(oblique, 'oblique.stl')))
err = np.degrees(np.arccos(min(1, abs(np.array(res[0]['direction']) @ d)))) if res else 180
check('oblique prism direction recovered within 1 deg', err < 1, f'({err:.3f} deg)')
box = trimesh.load(export(cq.Workplane().box(3, 2, 1).faces('>Z').workplane().hole(0.5), 'plate.stl'))
check('axis-aligned plate proposes no extra directions', detect_directions(box) == [])

# --- event slices -------------------------------------------------------------
from extract_sketches import event_slices  # noqa: E402

step = cq.Workplane().box(4, 4, 1, centered=(True, True, False)).faces('>Z').workplane().rect(2, 2).extrude(2)
ev = event_slices(trimesh.load(export(step, 'step.stl')), [0, 0, 1])
check('event slices hit both layers of a stepped block', len(ev) == 2 and abs(ev[0] - 0.5) < 1e-3 and abs(ev[1] - 2.0) < 1e-3,
      f'({np.round(ev, 3).tolist()})')

# --- cut phase ----------------------------------------------------------------
os.environ['CADFIT_EXACT_UNION'] = '1'
import cadquery_ops as co  # noqa: E402

gt = cq.Workplane().box(2, 1, 0.6).faces('>Z').workplane().rect(1, 0.5).cutBlind(-0.4)
gt_path = export(gt, 'gt.stl')
add = [{'type': 'pos', 'insts': [], 'height': 0.6, 'stl_path': export(cq.Workplane().box(2, 1, 0.6), 'box.stl'),
        'sketch_id': 'E0', 'candidate_id': 0}]
pool = [{'type': 'pos', 'insts': [], 'height': 0.4, 'sketch_id': 'cut:E1', 'candidate_id': 100001,
         'stl_path': export(cq.Workplane().box(1, 0.5, 0.4).translate((0, 0, 0.1)), 'pocket.stl')},
        {'type': 'pos', 'insts': [], 'height': 0.5, 'sketch_id': 'cut:E2', 'candidate_id': 100002,
         'stl_path': export(cq.Workplane().box(0.5, 0.5, 0.5).translate((0.9, 0, 0)), 'decoy.stl')}]
groups, v = co.cut_phase(add, pool, trimesh.load(gt_path), TMP)
cuts = [g['sketch_id'] for g in groups if g.get('op') == 'cut']
check('cut phase subtracts the pocket and skips the decoy', cuts == ['cut:E1'] and v > 0.999, f'({cuts}, iou={v:.4f})')

# --- beam search: add + cut composition ---------------------------------------
bdir = os.path.join(TMP, 'beam')
os.makedirs(bdir)
decoy_add = {'type': 'pos', 'insts': [], 'height': 0.3, 'sketch_id': 'E9', 'candidate_id': 9,
             'stl_path': export(cq.Workplane().box(0.4, 0.4, 0.3).translate((0.7, 0.2, 0)), 'dadd.stl')}
bg, bv = co.beam_search(add + [decoy_add], pool, trimesh.load(gt_path), bdir, width=3)
check('beam search finds box + pocket cut', bv is not None and bv > 0.999 and
      sorted(g['sketch_id'] for g in bg) == ['E0', 'cut:E1'], f'({[g["sketch_id"] for g in bg] if bg else None}, {bv})')
sg, sv = co.beam_search(add + [decoy_add], pool, trimesh.load(gt_path), bdir, width=3, seed=add + [decoy_add])
# (the decoy sits inside the pocket, so the cut makes it redundant rather than harmful)
check('seeded beam starts from the seed and adds the cut', sv is not None and sv > 0.999 and
      {'E0', 'cut:E1'} <= {g['sketch_id'] for g in sg}, f'({[g["sketch_id"] for g in sg] if sg else None}, {sv})')
sliver = {'type': 'revolve', 'insts': [], 'height': 0, 'sketch_id': 'cut:R4', 'candidate_id': 100004,
          'stl_path': export(cq.Workplane().box(1e-3, 1e-3, 1e-3).translate((0, 0, 0.2)), 'sliver.stl')}
ng, nv = co.beam_search(add + [decoy_add], pool + [sliver], trimesh.load(gt_path), bdir, width=3)
check('beam ignores a near-empty cut tool', nv is not None and 0.999 < nv <= 1.0 and
      'cut:R4' not in [g['sketch_id'] for g in ng], f'({[g["sketch_id"] for g in ng] if ng else None}, {nv})')
tg, tv = co.beam_search(add + [decoy_add], pool, trimesh.load(gt_path), bdir, width=3, seed=add, time_budget=0)
check('beam with no time left returns the seed', tg is not None and [g['sketch_id'] for g in tg] == ['E0'],
      f'({[g["sketch_id"] for g in tg] if tg else None}, {tv})')

# --- exact union IoU agrees with the strict judge ---------------------------
os.environ['CADFIT_CACHE_SOLIDS'] = '1'
# Candidates live in the pipeline's normalized frame, so the fixture's union is
# already centred with largest extent 2.
A = cq.Workplane().box(2, 1, 1).translate((0, 0, -0.5))
B = cq.Workplane().box(1, 1, 2).translate((0.5, 0, 0))
a, b = export(A, 'a.stl'), export(B, 'b.stl')
union_gt = export(A.union(B), 'ugt.stl')
gm = trimesh.load(union_gt)
udir = os.path.join(TMP, 'union')  # the GT is cached per output folder
os.makedirs(udir)
ex = co._exact_union_iou([{'stl_path': a}, {'stl_path': b}], gm, udir, 'u')
check('exact union of overlapping solids scores IoU 1 against their true union', ex is not None and abs(ex - 1) < 1e-4,
      f'({ex})')

# --- generic ops collapse into their own entries ---------------------------
from greedy_search import collapse_evaluated_operations  # noqa: E402

ev_ops = [{'type': 'extrude', 'sketch_idx': 0, 'iou': 0.3, 'height': 0.5, 'actions': ['A'], 'stl_path': 'e.stl'},
          {'type': 'generic', 'kind': 'loft', 'sketch_idx': 0, 'iou': 0.6, 'code': 'solid_gen_{N} = None',
           'actions': [], 'stl_path': 'g.stl'}]
pc = collapse_evaluated_operations(ev_ops, fix_sketch_identity=True)
ids = sorted(e['sketch_id'] for e in pc)
check('loft/sweep candidates get their own G entries', ids == ['E0', 'G0'] and
      next(e for e in pc if e['sketch_id'] == 'G0')['generic']['kind'] == 'loft', f'({ids})')
check('stock (positional) collapse ignores generic ops',
      all('generic' not in e for e in collapse_evaluated_operations(ev_ops, fix_sketch_identity=False)))

# --- persistent CadQuery worker gives identical STLs -----------------------
import hashlib  # noqa: E402

script = lambda out: ("import cadquery as cq\nresult = cq.Workplane().box(1,2,3).faces('>Z').workplane().hole(0.5)\n"
                      f"cq.exporters.export(result, '{out}')\n")
os.environ['CADFIT_CQ_WORKER'] = '0'
p0 = os.path.join(TMP, 'w0.stl')
co.execute_cadquery_script(script(p0), p0)
os.environ['CADFIT_CQ_WORKER'] = '1'
p1 = os.path.join(TMP, 'w1.stl')
co.execute_cadquery_script(script(p1), p1)
h = [hashlib.md5(open(p, 'rb').read()).hexdigest() for p in (p0, p1)]
check('persistent worker writes a byte-identical STL', h[0] == h[1])
check('persistent worker reports script failure', not co.execute_cadquery_script("raise ValueError('x')", os.path.join(TMP, 'n.stl')))

# --- loft/sweep code builds valid solids -------------------------------------
import analyze_sweep_loft as asl  # noqa: E402

t = np.linspace(0, 2 * np.pi, 48, endpoint=False)
sec = lambda z, r: np.stack([r * np.cos(t), r * np.sin(t), np.full_like(t, z)], 1)
out = os.path.join(TMP, 'loft.stl')
ok = co.execute_cadquery_script(co.generate_generic_script(asl.loft_code([sec(0, 1), sec(1, 0.5)]), out), out)
m = trimesh.load(out) if ok else None
cone = np.pi / 3 * (1 + 0.5 + 0.25)
check('loft code builds a frustum of the right volume', ok and abs(m.volume - cone) / cone < 0.01,
      f'({m.volume if m else None:.4f} vs {cone:.4f})' if ok else '')
path = np.stack([np.sin(np.linspace(0, 1, 8)) * 3, np.zeros(8), (1 - np.cos(np.linspace(0, 1, 8))) * 3], 1)[:, [2, 1, 0]]
out = os.path.join(TMP, 'sweep.stl')
prof = sec(0, 0.3) + path[0]
ok = co.execute_cadquery_script(co.generate_generic_script(asl.sweep_code(prof, [0, 0, 1], path, True), out), out)
check('sweep code builds a watertight solid', ok and trimesh.load(out).is_watertight)

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)

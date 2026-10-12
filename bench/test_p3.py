#!/usr/bin/env python3
"""Fast regression checks for the CADFit++ phase-3 additions.

  python bench/test_p3.py

Each check builds its own tiny CadQuery fixtures in a temp folder; nothing
depends on benchmark runs.
"""
import os
import sys
import tempfile
import time

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
t0 = time.time()
groups, v0 = co.cut_phase(add, pool, trimesh.load(gt_path), TMP, time_budget=0)
check('cut phase stops at its time budget with the model unchanged',
      groups == add and v0 is not None and time.time() - t0 < 5, f'({len(groups)} groups, iou={v0})')

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

# --- winding-number repair of an open mesh -----------------------------------
from gwn_repair import repair_to_winding_solid  # noqa: E402
# Raw ABC meshes are triangle soups: every triangle on its own vertices.
box = trimesh.creation.box((2.0, 1.0, 0.5))
open_box = trimesh.Trimesh(box.triangles.reshape(-1, 3), np.arange(3 * len(box.faces)).reshape(-1, 3), process=False)
open_box.export(os.path.join(TMP, 'open_box.stl'))
rp = repair_to_winding_solid(os.path.join(TMP, 'open_box.stl'), os.path.join(TMP, 'open_box_gwn.stl'),
                             cells_on_max_extent=48)
rs = trimesh.load(rp) if rp else None
check('winding repair turns a triangle-soup box into a closed solid of its volume and bounds',
      rs is not None and rs.is_watertight and abs(rs.volume - 1.0) < 0.05
      and np.allclose(rs.bounds, open_box.bounds, atol=1e-6),
      f'(vol {rs.volume:.4f}, watertight {rs.is_watertight})' if rs is not None else '(no solid)')

# A soup whose bounding box is set by an open sheet far from its solid: the
# stretch onto the input's bounds used to distort the solid (00002336).
sheet = trimesh.Trimesh([[-1, -0.5, 3.0], [1, -0.5, 3.0], [1, 0.5, 3.0]], [[0, 1, 2]], process=False)
trimesh.util.concatenate([open_box, sheet]).export(os.path.join(TMP, 'box_sheet.stl'))
rp = repair_to_winding_solid(os.path.join(TMP, 'box_sheet.stl'), os.path.join(TMP, 'box_sheet_gwn.stl'),
                             cells_on_max_extent=48)
check('winding repair declines (no stretch) when the solid does not fill the input bounds', rp is None
      and os.path.exists(os.path.join(TMP, 'box_sheet_gwn.stl.declined')))

# --- degenerate sketch loops -------------------------------------------------
import fit_primitives  # noqa: E402
# When every segment of a loop is shorter than the 1e-2 skip tolerance, only
# its moveTo is left; close() then raised "No start point specified - cannot
# close" and killed the whole candidate (raw ABC 00001607).
_p2i = fit_primitives.primitives_to_instances
calls = []
fit_primitives.primitives_to_instances = lambda *a: (calls.append(1), _p2i(*a) if len(calls) == 1
                                                     else ['sketch.moveTo(0.3, 0.3)'])[1]
square = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]
acts = fit_primitives.build_action_instances_from_entry(
    {'origin': [0, 0, 0], 'normal': [0, 0, 1], 'xdir': [1, 0, 0], 'loops_3d': [square, square]})
fit_primitives.primitives_to_instances = _p2i
check('a loop with no segments left is dropped, not emitted as moveTo + close',
      len(calls) == 2 and 'sketch.moveTo(0.3, 0.3)' not in acts, f'({acts[-2:]})')

# --- pool tasks that never return ---------------------------------------------
import multiprocessing as mp  # noqa: E402
import time  # noqa: E402
from cadquery_ops import safe_pool_map  # noqa: E402


def _task(x):
    if x == 'die':
        os._exit(1)        # a worker killed mid-task (segfault, OOM killer)
    if x == 'hang':
        time.sleep(3600)   # a deadlocked worker
    return x * 2


with mp.get_context('fork').Pool(2) as pool:
    t0 = time.time()
    res, lost = safe_pool_map(pool, _task, [1, 'die', 3], grace=3)
    check('safe_pool_map returns the finished results when a worker dies', res == [2, None, 6] and lost == 1
          and time.time() - t0 < 30, f'({res}, {time.time() - t0:.0f}s)')
with mp.get_context('fork').Pool(2) as pool:
    res, lost = safe_pool_map(pool, _task, [1, 'hang'], stall=3)
    check('safe_pool_map gives up on a task that stalls', res == [2, None] and lost == 1)
    res, lost = safe_pool_map(pool, _task, [1, 'hang'], deadline=time.time() + 3)
    check('safe_pool_map stops at the deadline', res == [2, None] and lost == 1)

# --- step timeouts kill the step's whole process tree --------------------------
import subprocess  # noqa: E402
from run_pipeline import _run_group  # noqa: E402
pidfile = os.path.join(TMP, 'grandchild.pid')
spawn = (f"import subprocess, sys, time; p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)']);"
         f"open({pidfile!r}, 'w').write(str(p.pid)); time.sleep(600)")
try:
    _run_group([sys.executable, '-c', spawn], timeout=5)
    timed_out = False
except subprocess.TimeoutExpired:
    timed_out = True
time.sleep(0.5)
gpid = int(open(pidfile).read())
try:
    os.kill(gpid, 0)
    alive = subprocess.run(['ps', '-o', 'stat=', '-p', str(gpid)], capture_output=True, text=True).stdout.strip()
    alive = bool(alive) and not alive.startswith('Z')
except ProcessLookupError:
    alive = False
check('a timed-out step leaves no grandchild running', timed_out and not alive)

# --- a pool whose task-queue lock is held by a stuck process can still be stopped
import threading  # noqa: E402
from cadquery_ops import abandon_pool  # noqa: E402


def _hold(lock):
    lock.acquire()
    time.sleep(600)


def _stop_in_thread(fn, pool, wait=10):
    t = threading.Thread(target=fn, args=(pool,), daemon=True)
    t0 = time.time()
    t.start()
    t.join(wait)
    return not t.is_alive(), time.time() - t0


_ctx = mp.get_context('fork')
_stuck = []
for stop in (lambda p: p.terminate(), abandon_pool):
    pool = _ctx.Pool(2)
    pool.map(_task, [1, 2])
    holder = _ctx.Process(target=_hold, args=(pool._inqueue._rlock,), daemon=True)
    holder.start()
    time.sleep(1)  # an idle worker gives the lock up to the holder only between tasks
    _stuck.append((stop, pool, holder))
ok_term, _ = _stop_in_thread(_stuck[0][0], _stuck[0][1], wait=8)
ok_ab, t_ab = _stop_in_thread(_stuck[1][0], _stuck[1][1], wait=30)
workers_dead = all(not w.is_alive() for w in _stuck[1][1]._pool)
for _, _, holder in _stuck:
    holder.kill()
check('abandon_pool stops a pool whose queue lock is held by a stuck process (terminate() hangs)',
      ok_ab and workers_dead, f'(terminate {"returned" if ok_term else "hung"}, abandon {t_ab:.1f}s)')

# --- a watchdog firing inside the target's wrap must not poison the cache ------
import iou  # noqa: E402
soup = trimesh.creation.box(extents=(2, 1, 1))
soup = trimesh.Trimesh(soup.vertices, soup.faces[:-2])  # open: needs the alpha-wrap
soup_path = os.path.join(TMP, 'open_box.stl')
soup.export(soup_path)


class _AlarmClient:
    def run(self, script, path=None, timeout=60.0):
        raise TimeoutError('Operation evaluation timed out')


_saved = iou._WRAP_CLIENT
iou._WRAP_CLIENT = _AlarmClient()
try:
    iou._cached_manifold(soup_path, True)
    raised = False
except TimeoutError:
    raised = True
iou._WRAP_CLIENT = _saved
cached = any(k[0] == soup_path for k in iou._MANIFOLD_CACHE)
box_path = os.path.join(TMP, 'half_box.stl')
trimesh.creation.box(extents=(1, 1, 1)).export(box_path)
v = iou.mesh_iou_cpu_boolean(soup_path, box_path, normalize=True)
check('a watchdog firing during the target wrap is re-raised, not cached as a failed target',
      raised and not cached and v > 0, f'(raised={raised}, cached={cached}, iou={v:.3f})')

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)

#!/usr/bin/env python3
"""Regression checks for the CADFit++ correctness fixes.

  python bench/test_fixes.py

Runs without CadQuery subprocesses; uses files from bench/ where a real case is
needed (the IoU>1 check needs bench/runs/arms_synth/stock/boss_on_plate_2/).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

results = []


def check(name, ok, detail=''):
    print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
    results.append(ok)


# --- sketch identity -------------------------------------------------------
from greedy_search import collapse_evaluated_operations  # noqa: E402

ext0 = {'type': 'extrude', 'sketch_idx': 0, 'iou': 0.30, 'height': 0.5, 'actions': ['CIRCLE_PROFILE'],
        'stl_path': 'e0.stl', 'origin': [0, 0, 0], 'normal': [0, 0, 1], 'xdir': [1, 0, 0]}
rev0 = {'type': 'revolve', 'sketch_idx': 0, 'iou': 0.90, 'angle': 360.0, 'actions': ['HALF_SECTION'],
        'axis_start': [0, 0, 0], 'axis_end': [0, 1, 0], 'stl_path': 'r0.stl',
        'origin': [0.1, 0, 0], 'normal': [1, 0, 0], 'xdir': [0, 1, 0]}

stock = collapse_evaluated_operations([ext0, rev0], fix_sketch_identity=False)
check('stock merges E0/R0 into one entry and hands the extrusion the revolve profile',
      len(stock) == 1 and stock[0]['insts'] == ['HALF_SECTION'] and stock[0]['pos_h'] == 0.5,
      '(documents the bug)')

fixed = collapse_evaluated_operations([ext0, rev0], fix_sketch_identity=True)
by_id = {e['sketch_id']: e for e in fixed}
check('fix keeps E0 and R0 as separate entries', set(by_id) == {'E0', 'R0'})
check('E0 keeps its own profile and STL',
      by_id.get('E0', {}).get('insts') == ['CIRCLE_PROFILE'] and by_id['E0'].get('pos_stl') == 'e0.stl'
      and by_id['E0'].get('revolve_angle') is None)
check('R0 keeps its own profile, STL and evaluation frame',
      by_id.get('R0', {}).get('insts') == ['HALF_SECTION'] and by_id['R0'].get('revolve_stl') == 'r0.stl'
      and by_id['R0'].get('revolve_origin') == [0.1, 0, 0] and by_id['R0'].get('pos_h') is None)

# The pruning side must then build each candidate from its own entry.
from cadquery_ops import _revolve_frame  # noqa: E402
check('pruning passes the recorded revolve frame', _revolve_frame(
    {'revolve_origin': [0.1, 0, 0], 'revolve_normal': [1, 0, 0], 'revolve_xdir': [0, 1, 0]}) ==
    {'origin': [0.1, 0, 0], 'normal': [1, 0, 0], 'xdir': [0, 1, 0]})
check('pruning falls back to stock frame recovery without the fix', _revolve_frame({'insts': []}) == {})

# --- IoU validity ------------------------------------------------------------
gt = 'bench/synthetic/boss_on_plate_2.stl'
cand = 'bench/runs/arms_synth/stock/boss_on_plate_2/best_greedy_parallel.stl'
if os.path.exists(gt) and os.path.exists(cand):
    import iou
    os.environ.pop('CADFIT_IOU_VALIDATE', None)
    iou._MANIFOLD_CACHE.clear()
    stock_iou = iou.mesh_iou_cpu_boolean(gt, cand, normalize=True)
    os.environ['CADFIT_IOU_VALIDATE'] = '1'
    iou._MANIFOLD_CACHE.clear()
    fixed_iou = iou.mesh_iou_cpu_boolean(gt, cand, normalize=True)
    check('stock IoU > 1 on the self-overlapping compound', stock_iou > 1.0, f'({stock_iou:.4f})')
    check('validated IoU is in [0, 1]', 0.0 < fixed_iou <= 1.0, f'({fixed_iou:.4f})')
    clean = 'bench/runs/arms_synth/stock/hex_prism_0/best_greedy_parallel.stl'
    if os.path.exists(clean):
        iou._MANIFOLD_CACHE.clear()
        a = iou.mesh_iou_cpu_boolean('bench/synthetic/hex_prism_0.stl', clean, normalize=True)
        os.environ.pop('CADFIT_IOU_VALIDATE', None)
        iou._MANIFOLD_CACHE.clear()
        b = iou.mesh_iou_cpu_boolean('bench/synthetic/hex_prism_0.stl', clean, normalize=True)
        check('validation leaves a clean volume unchanged', abs(a - b) < 1e-9, f'({a:.4f} vs {b:.4f})')
else:
    print('SKIP IoU validity (benchmark files not present)')

# --- timeout propagation ------------------------------------------------------
import cadquery_ops  # noqa: E402
import subprocess  # noqa: E402

orig = subprocess.Popen
class _Boom:  # noqa: E302
    def __init__(self, *a, **k):
        raise TimeoutError('Operation evaluation timed out')
subprocess.Popen = _Boom
try:
    cadquery_ops.execute_cadquery_script('x', '/nonexistent/out.stl', '/tmp/cadfit_test_script.py')
    check('SIGALRM TimeoutError propagates through execute_cadquery_script', False)
except TimeoutError:
    check('SIGALRM TimeoutError propagates through execute_cadquery_script', True)
finally:
    subprocess.Popen = orig
    try:
        os.remove('/tmp/cadfit_test_script.py')
    except OSError:
        pass

sys.exit(0 if all(results) else 1)

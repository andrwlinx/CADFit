#!/usr/bin/env python3
"""Build every candidate in a sweep_loft_candidates.json and print its IoU vs the GT.
Usage: python bench/eval_generic_cands.py cands.json gt.stl workdir"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cadquery_ops import execute_cadquery_script, compute_iou  # noqa: E402

cands, gt, work = json.load(open(sys.argv[1])), os.path.abspath(sys.argv[2]), os.path.abspath(sys.argv[3])
os.makedirs(work, exist_ok=True)
res = []
for i, c in enumerate(cands):
    out = f'{work}/g_{i}.stl'
    script = 'import cadquery as cq\n' + c['code'].replace('{N}', '1') + f"\nresult = solid_gen_1\ncq.exporters.export(result, '{out}')\n"
    ok = execute_cadquery_script(script, out, f'{work}/g_{i}.py')
    v = compute_iou(gt, out, normalize=True) if ok else None
    res.append((i, c['kind'], c.get('frenet'), c.get('bent'), c.get('n_sections'), None if v is None else round(v, 4)))
for r in res:
    print('RES', *r, file=sys.stderr)

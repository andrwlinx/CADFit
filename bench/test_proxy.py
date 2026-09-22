#!/usr/bin/env python3
"""Sanity checks: the ranker's kernel-free proxy IoU must agree with the
pipeline's boolean IoU (iou.mesh_iou_cpu_boolean) on shapes with known answers.

Usage: python bench/test_proxy.py
"""
import os
import sys
import tempfile

import numpy as np
import trimesh

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from iou import mesh_iou_cpu_boolean  # noqa: E402
import candidate_ranker as cr  # noqa: E402

TOL = 0.02


def boolean_iou(gt, cand):
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, 'gt.stl'), os.path.join(d, 'cand.stl')
        gt.export(a)
        cand.export(b)
        return mesh_iou_cpu_boolean(a, b, normalize=False, verbose=False)


def check(name, proxy, truth, analytic=None):
    ok = abs(proxy - truth) <= TOL and (analytic is None or abs(proxy - analytic) <= TOL)
    extra = '' if analytic is None else f' analytic={analytic:.4f}'
    print(f"{'PASS' if ok else 'FAIL'} {name}: proxy={proxy:.4f} boolean={truth:.4f}{extra}")
    return ok


def main():
    results = []

    # Extrude: GT box 2x1x1; candidate prism 1.2 x 1 (with a square hole) x 0.7 from the bottom face.
    gt = trimesh.creation.box(extents=(2, 1, 1))
    outer = [[-1, -0.5, -0.5], [0.2, -0.5, -0.5], [0.2, 0.5, -0.5], [-1, 0.5, -0.5]]
    hole = [[-0.6, -0.2, -0.5], [-0.2, -0.2, -0.5], [-0.2, 0.2, -0.5], [-0.6, 0.2, -0.5]]
    op = {'type': 'extrude', 'sketch_idx': 0, 'actions': [], 'height': 0.7, 't_min': 0.0, 't_max': 0.7,
          'origin': [0, 0, -0.5], 'normal': [0, 0, 1], 'xdir': [1, 0, 0]}
    meta = {'profile_3d': [outer, hole]}
    ctx = cr.build_context(gt, n_points=40000, seed=0)
    proxy = cr.extract_candidate_features(op, meta, ctx)['proxy_iou']
    solid = trimesh.creation.box(extents=(1.2, 1, 0.7))
    solid.apply_translation((-0.4, 0, -0.15))
    cut = trimesh.creation.box(extents=(0.4, 0.4, 0.7))
    cut.apply_translation((-0.4, 0, -0.15))
    cand = trimesh.boolean.difference([solid, cut], engine='manifold')
    v = (1.2 * 1 - 0.16) * 0.7
    results.append(check('extrude_with_hole', proxy, boolean_iou(gt, cand), analytic=v / 2.0))

    # Extrude that overshoots the GT: candidate height 1.5 on a 1-high box.
    op2 = dict(op, height=1.5, t_max=1.5)
    proxy = cr.extract_candidate_features(op2, {'profile_3d': [outer]}, ctx)['proxy_iou']
    results.append(check('extrude_overshoot', proxy, (1.2 * 1.0) / (2.0 + 1.2 * 0.5), analytic=None))

    # Revolve: GT cylinder r=1 h=2 about z; candidate = profile r in [0,0.8], z in [-1,0.5] swept 360.
    gt = trimesh.creation.cylinder(radius=1.0, height=2.0, sections=256)
    profile = [[0, 0, -1], [0.8, 0, -1], [0.8, 0, 0.5], [0, 0, 0.5]]
    op = {'type': 'revolve', 'sketch_idx': 0, 'actions': [], 'angle': 360.0}
    meta = {'profile_3d': [profile], 'axis_point': [0, 0, 0], 'axis_dir': [0, 0, 1]}
    ctx = cr.build_context(gt, n_points=40000, seed=0)
    proxy = cr.extract_candidate_features(op, meta, ctx)['proxy_iou']
    cand = trimesh.creation.cylinder(radius=0.8, height=1.5, sections=256)
    cand.apply_translation((0, 0, -0.25))
    results.append(check('revolve_cylinder', proxy, boolean_iou(gt, cand), analytic=0.64 * 1.5 / 2.0))

    # Ranking keeps the better of two candidates in one group and respects drop_tau.
    ops = [dict(op2, source='interval_0'), dict(op2, height=1.0, t_max=1.0, source='interval_1'),
           dict(op2, sketch_idx=1, origin=[50, 50, 50], source='interval_0')]
    metas = [{'profile_3d': [outer]}, {'profile_3d': [outer]},
             {'profile_3d': [(np.array(outer) + 50).tolist()]}]
    ctx = cr.build_context(trimesh.creation.box(extents=(2, 1, 1)), n_points=20000, seed=0)
    kept, diag = cr.rank_candidates(ops, metas, ctx, per_group_m=1, drop_tau=0.002)
    ok = [o['source'] for o in kept] == ['interval_1'] and diag[2]['group_dropped']
    print(f"{'PASS' if ok else 'FAIL'} selection: kept={[(o['sketch_idx'], o['source']) for o in kept]}")
    results.append(ok)

    sys.exit(0 if all(results) else 1)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Output equivalence of the tools-v3 exact rewrites against the tools-v2 code (commit f4435df),
on development inputs only (review-stage/TOOLS_V3_PROTOCOL.md, changes 1-4).

  git show f4435df:fit_primitives.py > OLD/fit_primitives_old.py   (likewise analyze_revolve_axis.py,
  git show f4435df:bench/score.py    > OLD/score_old.py             score.py)
  .venv/bin/python bench/tools_equivalence.py --old OLD --out results/tools/equivalence.json

Checks: (1) duplicate removal, 300 seeded random point sets; (2) revolve rotation, 200 seeded
cases, bit-identical; (3) robust judge, 18 target/reconstruction pairs from 6 development parts;
(4) profile fitting (build_action_instances_from_entry), every sketch extracted on 9 planes of
8 development parts, with total fitting time old vs new.
"""
import argparse
import json
import os
import sys
import tempfile
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--old', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--stl-dir', default=os.path.join(ROOT, 'bench', 'cadbench', 'fresh'))
    a = ap.parse_args()
    assert 'fresh2' not in a.stl_dir and 'fresh3' not in a.stl_dir
    os.environ['CADFIT_AGENT_EXEC'] = '1'
    sys.path[:0] = [a.old, os.path.join(ROOT, 'agent'), os.path.join(ROOT, 'bench'), ROOT]
    import analyze_revolve_axis as ara_new
    import analyze_revolve_axis_old as ara_old
    import fit_primitives as fp_new
    import fit_primitives_old as fp_old
    import score as sc_new
    import score_old as sc_old
    import trimesh
    out = {'old_commit': 'f4435df', 'stl_dir': os.path.relpath(a.stl_dir, ROOT)}

    rng = np.random.default_rng(0)
    same = 0
    for _ in range(300):
        n = int(rng.integers(1, 800))
        pts = rng.random((n, 2)) * rng.choice([1e-5, 1e-3, 1])
        k = int(rng.integers(0, n))
        pts = np.vstack([pts, pts[rng.integers(0, n, k)] + rng.normal(0, 4e-7, (k, 2))])
        rng.shuffle(pts)
        x, y = fp_old.remove_duplicate_points_2d(pts), fp_new.remove_duplicate_points_2d(pts)
        same += x.shape == y.shape and np.array_equal(x, y)
    out['dedup'] = {'cases': 300, 'identical': int(same)}

    rng = np.random.default_rng(1)
    same = 0
    for _ in range(200):
        P = rng.normal(size=(int(rng.integers(1, 500)), 3))
        ax, ang = rng.normal(size=3), float(rng.uniform(-180, 180))
        same += np.array_equal(ara_old.rotate_points_around_axis(P, None, ax, ang),
                               ara_new.rotate_points_around_axis(P, None, ax, ang))
    out['rotation'] = {'cases': 200, 'bit_identical': int(same)}

    parts = sorted(os.path.join(a.stl_dir, f) for f in os.listdir(a.stl_dir) if f.endswith('.stl'))
    tmp = tempfile.mkdtemp()
    same = n = 0
    for p in parts[:6]:
        g = trimesh.load(p, force='mesh')
        recons = []
        for k, s in enumerate((0.9, 1.0)):
            m = g.copy()
            m.apply_scale(s)
            recons.append(os.path.join(tmp, f'r{k}.stl'))
            m.export(recons[-1])
        b = trimesh.creation.box(extents=g.extents * 0.8)
        b.apply_translation(g.bounds.mean(0))
        recons.append(os.path.join(tmp, 'box.stl'))
        b.export(recons[-1])
        for r in recons:
            n += 1
            same += sc_old.robust_iou(p, r) == sc_new.robust_iou(p, r)
    out['judge'] = {'pairs': n, 'identical': int(same)}

    import skills
    n = same = 0
    t_old = t_new = 0.0
    for p in parts[:8]:
        ws = skills.SkillWorkspace(p, tempfile.mkdtemp())
        for nrm in ([0, 0, 1], [0, 1, 0], [1, 0, 0]):
            for off in (-0.3, 0.0, 0.3):
                try:
                    ws.extract_sketch(normal=nrm, offset=off)
                except Exception:
                    pass
        for e in ws.sketches.values():
            entry = {k: e[k] for k in ('origin', 'normal', 'xdir', 'loops_3d', 'loop_areas')}
            t = time.time()
            x = fp_old.build_action_instances_from_entry(json.loads(json.dumps(entry)))
            t_old += time.time() - t
            t = time.time()
            y = fp_new.build_action_instances_from_entry(json.loads(json.dumps(entry)))
            t_new += time.time() - t
            n += 1
            same += json.dumps(x, default=str) == json.dumps(y, default=str)
    out['fitting'] = {'parts': min(8, len(parts)), 'planes_per_part': 9, 'sketches': n, 'identical': int(same),
                      'seconds_old': round(t_old, 1), 'seconds_new': round(t_new, 1)}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, 'w'), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()

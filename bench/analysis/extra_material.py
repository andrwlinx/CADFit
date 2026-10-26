#!/usr/bin/env python3
"""Where is the delivered CAD's extra material? For each part: the share of the
CAD volume outside the target, and how much of that lies outside the target's
X/Y/Z silhouettes (what a silhouette trim could remove) vs inside all three
(filled pockets/holes a trim cannot see).

  python bench/analysis/extra_material.py <run_dir> <stl_dir> <part> [...]
"""
import glob
import os
import sys

import numpy as np
import trimesh
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
from shapely import vectorized

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import iou  # noqa: E402


def silhouette(mesh, axis):
    keep = [i for i in range(3) if i != axis]
    tris = mesh.vertices[mesh.faces][:, :, keep]
    polys = [Polygon(t) for t in tris if Polygon(t).area > 1e-12]
    return unary_union(polys).buffer(1e-3)


def main(run, stl_dir, parts):
    for p in parts:
        stl = glob.glob(os.path.join(stl_dir, p + '*.stl'))[0]
        name = os.path.basename(stl)[:-4]
        cad = os.path.join(run, name, 'best_greedy_parallel_iterative_cad.stl')
        if not os.path.exists(cad):
            cad = os.path.join(run, name, 'best_greedy_parallel_cad.stl')
        gt = iou.normalize_mesh(trimesh.load(stl, force='mesh'))
        rc = trimesh.load(cad, force='mesh')
        rng = np.random.default_rng(0)
        lo, hi = rc.bounds
        pts = rng.uniform(lo, hi, size=(200_000, 3))
        in_rc = rc.contains(pts) if rc.is_watertight else trimesh.proximity.signed_distance(rc, pts) > 0
        pts = pts[in_rc]
        in_gt = gt.contains(pts)
        extra = pts[~in_gt]
        outside_any = np.zeros(len(extra), bool)
        for ax in range(3):
            sil = silhouette(gt, ax)
            keep = [i for i in range(3) if i != ax]
            inside = vectorized.contains(sil, extra[:, keep[0]], extra[:, keep[1]])
            outside_any |= ~inside
        print(f'{p} cad_vol_pts {len(pts)} extra_frac {len(extra) / max(len(pts), 1):.3f} '
              f'extra_outside_silhouettes {outside_any.mean() if len(extra) else 0:.3f}', flush=True)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3:])

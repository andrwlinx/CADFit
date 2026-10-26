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
from scipy import ndimage

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import iou  # noqa: E402


RES = 1024
LO, HI = -1.05, 1.05  # normalized frame


def silhouette(mesh, axis):
    """Raster silhouette along `axis`: cells hit by dense surface samples, closed
    dilated one cell so the mask contains the true silhouette."""
    keep = [i for i in range(3) if i != axis]
    np.random.seed(1)
    pts = mesh.sample(3_000_000)[:, keep]
    ij = np.clip(((pts - LO) / (HI - LO) * RES).astype(int), 0, RES - 1)
    m = np.zeros((RES, RES), bool)
    m[ij[:, 0], ij[:, 1]] = True
    m = ndimage.binary_closing(m, iterations=2)
    return ndimage.binary_dilation(m, iterations=1)


def in_mask(mask, xy):
    ij = np.clip(((xy - LO) / (HI - LO) * RES).astype(int), 0, RES - 1)
    return mask[ij[:, 0], ij[:, 1]]


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
        pts = rng.uniform(lo, hi, size=(60_000, 3))
        in_rc = rc.contains(pts) if rc.is_watertight else trimesh.proximity.signed_distance(rc, pts) > 0
        pts = pts[in_rc]
        in_gt = gt.contains(pts)
        extra = pts[~in_gt]
        outside_any = np.zeros(len(extra), bool)
        for ax in range(3):
            keep = [i for i in range(3) if i != ax]
            outside_any |= ~in_mask(silhouette(gt, ax), extra[:, keep])
        print(f'{p} cad_vol_pts {len(pts)} extra_frac {len(extra) / max(len(pts), 1):.3f} '
              f'extra_outside_silhouettes {outside_any.mean() if len(extra) else 0:.3f}', flush=True)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3:])

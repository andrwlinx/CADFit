#!/usr/bin/env python3
"""
Attribute reconstruction error to ground-truth surface types.

For each part: missing = GT - recon, extra = recon - GT (manifold booleans on
alpha-wrapped meshes, GT normalized to [-1,1] like the pipeline). Each residual
body is split into connected components; a component's volume is assigned to
the GT surface type nearest to it (area-weighted vote of its surface samples
against labelled samples of the tessellated GT STEP faces).

The per-type totals say where the missing IoU actually lives, e.g. "40% of
missing volume sits against bspline faces" -> loft/sweep is worth building.

Usage:
  python bench/residual_attribution.py --runs <run_dir> --gt-dir bench/cadbench/dev \
      [--recon best_greedy_parallel_iterative.stl] [--out attribution.json]
"""
import argparse
import glob
import json
import os
import sys
from collections import defaultdict

import numpy as np
import trimesh
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import iou  # noqa: E402

RECON_NAMES = ('best_greedy_parallel_iterative.stl', 'best_greedy_parallel.stl')


def labelled_gt_samples(step_path, center, scale, n=60000, seed=0):
    """Sample points on the GT STEP faces, each labelled with its surface type."""
    import cadquery as cq
    shape = cq.importers.importStep(step_path).val()
    verts, faces, labels = [], [], []
    for f in shape.Faces():
        try:
            v, t = f.tessellate(1e-3 / max(scale, 1e-9), 0.2)
        except Exception:
            continue
        if not t:
            continue
        off = sum(len(x) for x in verts)
        verts.append(np.array([p.toTuple() for p in v]))
        faces.append(np.array(t) + off)
        labels += [f.geomType().lower()] * len(t)
    if not verts:
        return None, None
    m = trimesh.Trimesh(np.vstack(verts), np.vstack(faces), process=False)
    m.apply_translation(-center)
    m.apply_scale(scale)
    pts, fi = trimesh.sample.sample_surface(m, n, seed=seed)
    return pts, np.array(labels)[fi]


def residual_components(a, b):
    """Components of manifold difference a - b as trimeshes."""
    diff = a - b
    if diff.is_empty():
        return []
    mesh = diff.to_mesh()
    tm = trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts), process=False)
    return [c for c in tm.split(only_watertight=False) if abs(c.volume) > 1e-7]


def attribute(components, tree, labels, k=8, seed=0):
    out = defaultdict(float)
    for c in components:
        vol = abs(c.volume)
        pts, _ = trimesh.sample.sample_surface(c, 400, seed=seed)
        _, idx = tree.query(pts, k=k)
        vote = defaultdict(int)
        for lab in labels[idx].ravel():
            vote[lab] += 1
        total = sum(vote.values())
        for lab, v in vote.items():
            out[lab] += vol * v / total
    return dict(out)


def analyse(gt_stl, gt_step, recon_stl):
    gt = trimesh.load(gt_stl, force='mesh')
    bmin, bmax = gt.bounds
    center = 0.5 * (bmin + bmax)
    scale = 2.0 / float((bmax - bmin).max())
    iou.normalize_mesh(gt)
    ma = iou._to_manifold(iou._alpha_wrap(gt))
    mb = iou._to_manifold(iou._alpha_wrap(trimesh.load(recon_stl, force='mesh')))
    if ma is None or mb is None:
        return {'error': 'manifold failed'}
    pts, labels = labelled_gt_samples(gt_step, center, scale)
    if pts is None:
        return {'error': 'step tessellation failed'}
    tree = cKDTree(pts)
    vgt = abs(ma.volume())
    missing = attribute(residual_components(ma, mb), tree, labels)
    extra = attribute(residual_components(mb, ma), tree, labels)
    return {'vol_gt': vgt,
            'missing': {k: v / vgt for k, v in missing.items()},
            'extra': {k: v / vgt for k, v in extra.items()},
            'missing_total': sum(missing.values()) / vgt,
            'extra_total': sum(extra.values()) / vgt}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--runs', required=True, help='pipeline output folder (one subfolder per part)')
    ap.add_argument('--gt-dir', required=True, help='folder with <id>.stl and <id>.step')
    ap.add_argument('--recon', default=None)
    ap.add_argument('--out')
    args = ap.parse_args()

    results = {}
    for step in sorted(glob.glob(os.path.join(args.gt_dir, '*.step'))):
        key = os.path.splitext(os.path.basename(step))[0]
        names = [args.recon] if args.recon else RECON_NAMES
        recon = next((os.path.join(args.runs, key, n) for n in names
                      if os.path.exists(os.path.join(args.runs, key, n))), None)
        if recon is None:
            continue
        r = analyse(os.path.join(args.gt_dir, key + '.stl'), step, recon)
        results[key] = r
        if 'error' in r:
            print(f'{key}: {r["error"]}', file=sys.stderr)
            continue
        top = sorted(r['missing'].items(), key=lambda x: -x[1])[:3]
        print(f'{key:<48} miss={r["missing_total"]:.3f} extra={r["extra_total"]:.3f} '
              f'miss_by=' + ','.join(f'{k}:{v:.3f}' for k, v in top), file=sys.stderr)

    ok = [r for r in results.values() if 'error' not in r]
    for kind in ('missing', 'extra'):
        agg = defaultdict(float)
        for r in ok:
            for k, v in r[kind].items():
                agg[k] += v / max(len(ok), 1)
        print(f'mean {kind} (fraction of GT volume): ' +
              ', '.join(f'{k}={v:.4f}' for k, v in sorted(agg.items(), key=lambda x: -x[1])), file=sys.stderr)
    if args.out:
        json.dump(results, open(args.out, 'w'), indent=1)


if __name__ == '__main__':
    main()

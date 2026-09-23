#!/usr/bin/env python3
"""
Independent quality judge for benchmark arms.

Scores a reconstruction against its ground truth with alpha-wrap forced on BOTH
meshes before the manifold boolean, so the result cannot be inflated by the
self-overlap failure in stock `iou.py`, and reports the volume identity check.
Used for every arm so a metric bug cannot flatter any of them.

Usage:
  python bench/score.py <gt.stl> <recon.stl>
  python bench/score.py --arms bench/runs/arms_synth --stl-dir bench/synthetic [--out scores.json]
"""
import argparse
import glob
import json
import os
import sys

import trimesh

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import iou  # noqa: E402


def strict_iou(gt_path, recon_path):
    gt = iou.normalize_mesh(trimesh.load(gt_path, force='mesh'))
    rc = trimesh.load(recon_path, force='mesh')
    ma = iou._to_manifold(iou._alpha_wrap(gt))
    mb = iou._to_manifold(iou._alpha_wrap(rc))
    if ma is None or mb is None:
        return {'iou': 0.0, 'consistent': False, 'note': 'manifold construction failed'}
    vols = iou._boolean_volumes(ma, mb)
    if vols is None:
        return {'iou': 0.0, 'consistent': False, 'note': 'boolean failed'}
    v_inter, v_uni = vols
    ok = iou._volumes_consistent(ma, mb, v_inter, v_uni)
    return {'iou': (v_inter / v_uni) if v_uni > 0 else 0.0, 'consistent': bool(ok),
            'vol_gt': abs(ma.volume()), 'vol_recon': abs(mb.volume()), 'inter': v_inter, 'union': v_uni}


def main():
    ap = argparse.ArgumentParser(description='Strict IoU judge')
    ap.add_argument('paths', nargs='*')
    ap.add_argument('--arms', help='arms folder from bench/run_arms.sh')
    ap.add_argument('--stl-dir')
    ap.add_argument('--recon', default='best_greedy_parallel.stl')
    ap.add_argument('--out')
    args = ap.parse_args()

    if args.arms:
        out = {}
        for done in sorted(glob.glob(os.path.join(args.arms, '*', '*', 'done'))):
            folder = os.path.dirname(done)
            arm, part = folder.split(os.sep)[-2:]
            gt = os.path.join(args.stl_dir, part + '.stl')
            recon = os.path.join(folder, args.recon)
            if not (os.path.exists(gt) and os.path.exists(recon)):
                out.setdefault(arm, {})[part] = None
                continue
            r = strict_iou(gt, recon)
            out.setdefault(arm, {})[part] = r
            print(f"{arm:<14} {part:<22} iou={r['iou']:.4f} consistent={r['consistent']}")
        if args.out:
            json.dump(out, open(args.out, 'w'), indent=2)
    else:
        gt, recon = args.paths
        print(json.dumps(strict_iou(gt, recon), indent=2))


if __name__ == '__main__':
    main()

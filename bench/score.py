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
  python bench/score.py --runs bench/runs/A bench/runs/B --stl-dir bench/cadbench/smoke
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


RUN_RECON = ('best_greedy_parallel_iterative.stl', 'best_greedy_parallel.stl')


def chamfer(gt_path, recon_path, n=20000, seed=0):
    """Symmetric mean L2 chamfer distance in the normalized [-1,1] frame."""
    from scipy.spatial import cKDTree
    gt = iou.normalize_mesh(trimesh.load(gt_path, force='mesh'))
    rc = trimesh.load(recon_path, force='mesh')
    a, _ = trimesh.sample.sample_surface(gt, n, seed=seed)
    b, _ = trimesh.sample.sample_surface(rc, n, seed=seed)
    return float(0.5 * (cKDTree(b).query(a)[0].mean() + cKDTree(a).query(b)[0].mean()))


def score_runs(run_dirs, stl_dir):
    """Score full-pipeline output folders (run_pipeline.py --output-folder).
    A part with no reconstruction counts as invalid with IoU 0."""
    parts = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(stl_dir, '*.stl')))
    out = {}
    for run in run_dirs:
        name = os.path.basename(run.rstrip('/'))
        if not any(os.path.isdir(os.path.join(run, p)) for p in parts):
            continue  # an input copy or code snapshot folder, not a run
        res = {}
        for part in parts:
            recon = next((os.path.join(run, part, r) for r in RUN_RECON
                          if os.path.exists(os.path.join(run, part, r))), None)
            if recon is None:
                if os.path.isdir(os.path.join(run, part)):
                    res[part] = {'iou': 0.0, 'cd': None, 'valid': False}
                continue
            gt = os.path.join(stl_dir, part + '.stl')
            r = strict_iou(gt, recon)
            r['cd'] = chamfer(gt, recon)
            r['valid'] = True
            res[part] = r
            print(f"{name:<22} {part[:40]:<40} iou={r['iou']:.4f} cd={r['cd']:.4f}")
        out[name] = res
    common = set.intersection(*(set(v) for v in out.values())) if out else set()
    print(f'\n{len(common)} parts scored by every run')
    for name, res in out.items():
        ious = [res[p]['iou'] for p in common]
        cds = [res[p]['cd'] for p in common if res[p]['cd'] is not None]
        inval = sum(not res[p]['valid'] for p in common)
        if ious:
            print(f'{name:<22} mean IoU {sum(ious) / len(ious):.4f}  mean CD {sum(cds) / max(len(cds), 1):.4f}  invalid {inval}')
    return out


def main():
    ap = argparse.ArgumentParser(description='Strict IoU judge')
    ap.add_argument('paths', nargs='*')
    ap.add_argument('--arms', help='arms folder from bench/run_arms.sh')
    ap.add_argument('--runs', nargs='+', help='full-pipeline output folders to score side by side')
    ap.add_argument('--stl-dir')
    ap.add_argument('--recon', default='best_greedy_parallel.stl')
    ap.add_argument('--out')
    args = ap.parse_args()

    if args.runs:
        out = score_runs(args.runs, args.stl_dir)
        if args.out:
            json.dump(out, open(args.out, 'w'), indent=2)
    elif args.arms:
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

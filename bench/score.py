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
import subprocess
import sys

import trimesh

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import iou  # noqa: E402


def _gwn(mesh, Q, max_elems=1_000_000):
    """Generalized winding number of each query point (Jacobson et al. 2013):
    ~1 inside, ~0 outside, robust to cracks and duplicate shells. Queries are
    chunked so each (queries x triangles x 3) temporary stays near
    `max_elems` entries whatever the mesh size."""
    import numpy as np
    T = mesh.triangles
    chunk = max(1, max_elems // max(len(T), 1))
    out = np.zeros(len(Q))
    for s in range(0, len(Q), chunk):
        q = Q[s:s + chunk]
        a = T[None, :, 0, :] - q[:, None, :]
        b = T[None, :, 1, :] - q[:, None, :]
        c = T[None, :, 2, :] - q[:, None, :]
        la, lb, lc = (np.linalg.norm(x, axis=2) for x in (a, b, c))
        det = np.einsum('ijk,ijk->ij', a, np.cross(b, c))
        den = (la * lb * lc + np.einsum('ijk,ijk->ij', a, b) * lc
               + np.einsum('ijk,ijk->ij', b, c) * la + np.einsum('ijk,ijk->ij', c, a) * lb)
        out[s:s + chunk] = (2 * np.arctan2(det, den)).sum(1) / (4 * np.pi)
    return out


def robust_iou(gt_path, recon_path, n=40000, seed=0):
    """Judge that does not depend on how clean the reconstruction's STL is.

    GT (a clean CADBench solid) is normalized to [-1,1]. If the reconstruction
    is a closed, consistently wound volume, IoU is exact (manifold3d booleans,
    bodies unioned). Otherwise, e.g. an exact-union result cracked by the
    STL float32 round trip, IoU is a seeded Monte Carlo estimate in which the
    reconstruction's inside test is the generalized winding number. (Alpha-wrap
    turns such meshes into hollow shells: 0.078 against a true ~0.91.)"""
    import numpy as np
    gt = iou.normalize_mesh(trimesh.load(gt_path, force='mesh'))
    rc = trimesh.load(recon_path, force='mesh')
    ma = iou._to_manifold(gt) if gt.is_watertight else None
    if ma is None:
        ma = iou._to_manifold(iou._alpha_wrap(gt))
    closed = rc.is_watertight and rc.is_winding_consistent and rc.volume > 0
    mb = None
    if closed:
        mb = iou._bodies_union_manifold(rc) if rc.body_count > 1 else iou._to_manifold(rc)
    if ma is not None and mb is not None:
        vols = iou._boolean_volumes(ma, mb)
        if vols is not None and iou._volumes_consistent(ma, mb, *vols):
            return {'iou': vols[0] / vols[1] if vols[1] > 0 else 0.0, 'method': 'exact'}
    lo = np.minimum(gt.bounds[0], rc.bounds[0]) - 0.01
    hi = np.maximum(gt.bounds[1], rc.bounds[1]) + 0.01
    Q = np.random.default_rng(seed).uniform(lo, hi, (n, 3))
    if gt.is_watertight:  # ray-cast containment; chunked, its memory grows with rays x hits
        in_gt = np.concatenate([gt.contains(Q[s:s + 4000]) for s in range(0, len(Q), 4000)])
    else:
        in_gt = _gwn(gt, Q) > 0.5
    in_rc = _gwn(rc, Q) > 0.5
    u = (in_gt | in_rc).sum()
    return {'iou': float((in_gt & in_rc).sum() / u) if u else 0.0, 'method': 'gwn-mc'}


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


JUDGE = 'robust'   # --judge wrap restores the phase-2 alpha-wrap judge
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
    ps = subprocess.run(['ps', '-Ao', 'command'], capture_output=True, text=True).stdout
    running = {p for p in parts if p + '.stl' in ps}
    out = {}
    for run in run_dirs:
        name = os.path.basename(run.rstrip('/'))
        if not any(os.path.isdir(os.path.join(run, p)) for p in parts):
            continue  # an input copy or code snapshot folder, not a run
        res = {}
        for part in parts:
            if part in running and not os.path.exists(os.path.join(run, part, 'final_iou.json')):
                continue  # still running: its STLs are intermediate (a crash still scores invalid)
            recon = next((os.path.join(run, part, r) for r in RUN_RECON
                          if os.path.exists(os.path.join(run, part, r))), None)
            if recon is None:
                if os.path.isdir(os.path.join(run, part)):
                    res[part] = {'iou': 0.0, 'cd': None, 'valid': False}
                continue
            gt = os.path.join(stl_dir, part + '.stl')
            r = robust_iou(gt, recon) if JUDGE == 'robust' else strict_iou(gt, recon)
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
    ap.add_argument('--judge', choices=['robust', 'wrap'], default='robust',
                    help='robust: exact booleans, winding-number MC for unclean meshes (default); '
                         'wrap: alpha-wrap both meshes (phase-2 judge)')
    args = ap.parse_args()
    global JUDGE
    JUDGE = args.judge

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
        print(json.dumps(robust_iou(gt, recon) if JUDGE == 'robust' else strict_iou(gt, recon), indent=2))


if __name__ == '__main__':
    main()

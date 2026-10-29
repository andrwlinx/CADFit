#!/usr/bin/env python3
"""
Surface agreement between the delivered CAD and the input mesh, per part.

  python bench/detail_scores.py --runs dev3_d0 dev4_v2 --scores bench/runs/dev34_scores.json \
      --stl-dir bench/cadbench/fresh --jobs 16 --out bench/runs/detail_dev34.json

For each part the CAD that score.py --cad rebuilt (<recon>_cad.stl) is compared
with the input mesh in the normalized frame (largest extent spans [-1, 1], so
0.01 is 0.5% of the part size):

  within_half / within_1pct   share of the input surface within 0.01 / 0.02 of the CAD
  cad_within_half             share of the CAD surface within 0.01 of the input (no extra material)
  fscore_half                 harmonic mean of within_half and cad_within_half
  chamfer                     mean of the two one-sided mean distances
  sweep                       {tau: {recall, precision, fscore}} for tau in TAUS
                              (both directions use the boundary of the volume the
                               CAD occupies: the program's solids fused with OCC,
                               bench/union_replay.py, else union_boundary's
                               winding-number filter)
                              (recall = input surface within tau of the CAD,
                               precision = CAD surface within tau of the input)

Distances are exact point-to-surface distances from 100k samples of one surface
to the other mesh (exact=False: nearest-neighbour distances to dense samples,
which under-count recall at small tau on large-area parts). A part whose CAD does not build, or is not OCC-valid in the scores
file, gets 0 for every share (as the validity-gated IoU does) and its raw
numbers under "ungated".
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import trimesh
from concurrent.futures import ProcessPoolExecutor
from scipy.spatial import cKDTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import iou  # noqa: E402

HALF, ONE = 0.01, 0.02
TAUS = (0.005, 0.01, 0.02, 0.04)  # 0.25%, 0.5%, 1%, 2% of the part size
N_GT, N_CAD = 200_000, 3_000_000
N_EXACT = 100_000  # samples per side with exact distances (share error ~0.0016 at p=0.5)
RECON = ('best_greedy_parallel_iterative', 'best_greedy_parallel')  # score.py RUN_RECON order


def _sides(cad, pts, nrm, eps):
    """Per point: is the point `eps` along / against the normal inside the CAD."""
    from gwn_repair import _gwn_fast
    return _gwn_fast(cad, pts + eps * nrm) > 0.5, _gwn_fast(cad, pts - eps * nrm) > 0.5


def union_boundary(cad, max_edge=0.004, eps=2e-4, max_levels=12):
    """The boundary of the volume the CAD occupies, as a triangle mesh. A CAD of
    several solids (a compound the judge unions) carries faces buried inside the
    union, and an STL roundtrip can merge such solids into one connected body, so
    body counts say nothing about it. A surface point is boundary when exactly one
    side of it is inside the CAD (generalized winding number of the points `eps`
    off its two sides): faces between overlapping or touching solids (inside on
    both sides) go, cavity walls stay. Each triangle is probed at its centroid and
    near its corners. One whose probes agree is kept or dropped whole; one whose
    probes disagree straddles another solid and is split in four, recursively,
    until its edges are under `max_edge`, where its centroid decides. The work
    follows the curves where solids meet, not the surface area."""
    tri = cad.triangles
    nrm = cad.face_normals
    kept = []
    for level in range(max_levels + 1):
        if not len(tri):
            break
        c = tri.mean(axis=1)
        probes = np.concatenate([c] + [c + 0.9 * (tri[:, k] - c) for k in range(3)])
        nn = np.tile(nrm, (4, 1))
        a, b = _sides(cad, probes, nn, eps)
        status = (a != b).reshape(4, -1).T
        whole, none = status.all(axis=1), ~status.any(axis=1)
        kept.append(tri[whole])
        mixed = ~whole & ~none
        edge = np.linalg.norm(tri[:, [1, 2, 0]] - tri, axis=2).max(axis=1)
        last = mixed & ((edge <= max_edge) | (level == max_levels))
        kept.append(tri[last & status[:, 0]])  # small enough: the centroid decides
        split = mixed & ~last
        t, n = tri[split], nrm[split]
        m01, m12, m20 = (t[:, 0] + t[:, 1]) / 2, (t[:, 1] + t[:, 2]) / 2, (t[:, 2] + t[:, 0]) / 2
        tri = np.concatenate([np.stack([t[:, 0], m01, m20], 1), np.stack([m01, t[:, 1], m12], 1),
                              np.stack([m20, m12, t[:, 2]], 1), np.stack([m01, m12, m20], 1)])
        nrm = np.tile(n, (4, 1))
    tris = np.concatenate(kept) if kept else np.zeros((0, 3, 3))
    if not len(tris):
        return None
    return trimesh.Trimesh(tris.reshape(-1, 3), np.arange(len(tris) * 3).reshape(-1, 3), process=False)


def detail(gt_path, cad_path, seed=0, n_cad=None, exact=True, boundary_path=None):
    n_cad = n_cad or N_CAD
    np.random.seed(seed)
    gt = iou.normalize_mesh(trimesh.load(gt_path, force='mesh'))
    cad = trimesh.load(cad_path, force='mesh')
    if exact:
        # Exact point-to-surface distances: no dependence on how densely the other
        # surface is sampled (KD distances to samples did not converge at tau 0.005
        # on large-area parts: 00883892 recall 0.42 / 0.75 / 0.89 at 1M / 3M / 6M).
        # The occupied volume's boundary: the fused solids when given (union_replay.py),
        # else the winding-number filter.
        bnd = trimesh.load(boundary_path, force='mesh') if boundary_path else union_boundary(cad)
        if bnd is None:
            raise ValueError('CAD encloses no volume')
        d_gc = trimesh.proximity.closest_point(bnd, gt.sample(N_EXACT))[1]
        d_cg = trimesh.proximity.closest_point(gt, bnd.sample(N_EXACT))[1]
    else:
        g, c = gt.sample(N_GT), cad.sample(n_cad)
        d_gc = cKDTree(c).query(g, workers=1)[0]
        d_cg = cKDTree(gt.sample(n_cad)).query(cad.sample(N_GT), workers=1)[0]
    wh, ch = float((d_gc <= HALF).mean()), float((d_cg <= HALF).mean())
    sweep = {}
    for tau in TAUS:
        r, p = float((d_gc <= tau).mean()), float((d_cg <= tau).mean())
        sweep[str(tau)] = {'recall': r, 'precision': p, 'fscore': 2 * r * p / (r + p) if r + p else 0.0}
    return {'within_half': wh, 'within_1pct': float((d_gc <= ONE).mean()), 'cad_within_half': ch,
            'fscore_half': 2 * wh * ch / (wh + ch) if wh + ch else 0.0,
            'chamfer': float((d_gc.mean() + d_cg.mean()) / 2), 'sweep': sweep}


def _zero(status, **extra):
    z = {'recall': 0.0, 'precision': 0.0, 'fscore': 0.0}
    return {'status': status, 'within_half': 0.0, 'within_1pct': 0.0, 'cad_within_half': 0.0, 'fscore_half': 0.0,
            'sweep': {str(t): dict(z) for t in TAUS}, **extra}


def fused_boundary(stem, timeout=1800):
    """<stem>_union.stl: the program's solids fused and tessellated (union_replay.py),
    made once and cached with its record in <stem>_union.json; None if it fails."""
    import subprocess
    out, rec_path = stem + '_union.stl', stem + '_union.json'
    if not os.path.exists(rec_path):
        if not os.path.exists(stem + '.py'):
            return None
        try:
            p = subprocess.run([sys.executable, os.path.join(ROOT, 'bench', 'union_replay.py'), stem + '.py', out],
                               capture_output=True, text=True, timeout=timeout, cwd=os.path.dirname(stem))
            rec = json.loads(p.stdout.strip().splitlines()[-1])
        except (subprocess.TimeoutExpired, IndexError, json.JSONDecodeError) as e:
            rec = {'built': False, 'error': f'{type(e).__name__}'}
        json.dump(rec, open(rec_path, 'w'))
    rec = json.load(open(rec_path))
    return out if rec.get('built') and os.path.exists(out) else None


def one(job):
    run, part, gt, valid, n_cad, seed = job
    os.environ['OMP_NUM_THREADS'] = '1'
    stem = next((os.path.join(run, part, r) for r in RECON if os.path.exists(os.path.join(run, part, r + '.stl'))),
                None)
    cad = stem + '_cad.stl' if stem else None
    if not cad or not os.path.exists(cad):
        return run, part, _zero('no_cad')
    # Per-part cache, so a preempted job resumes instead of starting over.
    cache = f'{stem}_detail_s{seed}_n{n_cad}.json'
    if os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(cad):
        d = json.load(open(cache))
    else:
        try:
            fb = fused_boundary(stem)
            if fb is None and not valid:
                # Gated to 0 either way; the winding fallback on a large compound that
                # does not fuse can take half an hour for a diagnostic-only number.
                return run, part, _zero('invalid', ungated=None)
            d = detail(gt, cad, seed=seed, n_cad=n_cad, boundary_path=fb)
            d['boundary'] = 'fused' if fb else 'winding'
        except Exception as e:  # noqa: BLE001
            return run, part, _zero(f'error: {type(e).__name__}: {e}')
        json.dump(d, open(cache, 'w'))
    if valid:
        return run, part, {'status': 'valid', **d}
    return run, part, _zero('invalid', ungated=d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', nargs='+', required=True, help='run names under bench/runs')
    ap.add_argument('--scores', required=True, help='score.py --cad output (for cad_valid)')
    ap.add_argument('--stl-dir', required=True)
    ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--out', required=True)
    ap.add_argument('--n-cad', type=int, default=N_CAD, help='CAD surface samples (convergence check)')
    ap.add_argument('--parts', nargs='*', help='only these part-name prefixes')
    ap.add_argument('--seed', type=int, default=0, help='surface-sampling seed (repeatability check)')
    a = ap.parse_args()
    scores = json.load(open(a.scores))
    parts = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(a.stl_dir, '*.stl')))
    if a.parts:
        parts = [p for p in parts if any(p.startswith(q) for q in a.parts)]
    jobs = [(os.path.join(ROOT, 'bench', 'runs', r), p, os.path.join(a.stl_dir, p + '.stl'),
             bool(scores[r].get(p, {}).get('cad_valid')), a.n_cad, a.seed) for r in a.runs for p in parts]
    out = {r: {} for r in a.runs}
    with ProcessPoolExecutor(a.jobs) as ex:
        for run, part, rec in ex.map(one, jobs):
            out[os.path.basename(run)][part] = rec
            print(os.path.basename(run), part, rec['status'], round(rec['within_half'], 4), flush=True)
    json.dump(out, open(a.out, 'w'), indent=1)
    for r in a.runs:
        v = list(out[r].values())
        print(r, {k: round(float(np.mean([x[k] for x in v])), 4) for k in ('within_half', 'within_1pct', 'fscore_half')})


if __name__ == '__main__':
    main()

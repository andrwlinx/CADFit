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
                              (precision samples the CAD's outer boundary only:
                               faces buried in a compound's union are not surface)
                              (recall = input surface within tau of the CAD,
                               precision = CAD surface within tau of the input)

Distances are nearest-neighbour distances to dense surface samples (spacing
~0.001). A part whose CAD does not build, or is not OCC-valid in the scores
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
RECON = ('best_greedy_parallel_iterative', 'best_greedy_parallel')  # score.py RUN_RECON order


def boundary_samples(cad, n, eps=1e-3):
    """Surface samples of the CAD's outer boundary. A CAD of several overlapping
    solids (a compound the judge unions) has faces buried inside the union; they
    are not surface of the delivered shape and would count as extra material.
    A sample is kept when the point just off it on one side is outside the CAD
    (generalized winding number < 0.5)."""
    if cad.body_count <= 1:
        return cad.sample(n)
    from gwn_repair import _gwn_fast
    pts, fi = trimesh.sample.sample_surface(cad, int(n * 1.5))
    nrm = cad.face_normals[fi]
    out = np.minimum(_gwn_fast(cad, pts + eps * nrm), _gwn_fast(cad, pts - eps * nrm)) < 0.5
    return pts[out][:n]


def detail(gt_path, cad_path, seed=0, n_cad=None):
    n_cad = n_cad or N_CAD
    np.random.seed(seed)
    gt = iou.normalize_mesh(trimesh.load(gt_path, force='mesh'))
    cad = trimesh.load(cad_path, force='mesh')
    g, c = gt.sample(N_GT), cad.sample(n_cad)
    d_gc = cKDTree(c).query(g, workers=1)[0]
    d_cg = cKDTree(gt.sample(n_cad)).query(boundary_samples(cad, N_GT), workers=1)[0]
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


def one(job):
    run, part, gt, valid, n_cad = job
    os.environ['OMP_NUM_THREADS'] = '1'
    stem = next((os.path.join(run, part, r) for r in RECON if os.path.exists(os.path.join(run, part, r + '.stl'))),
                None)
    cad = stem + '_cad.stl' if stem else None
    if not cad or not os.path.exists(cad):
        return run, part, _zero('no_cad')
    try:
        d = detail(gt, cad, n_cad=n_cad)
    except Exception as e:  # noqa: BLE001
        return run, part, _zero(f'error: {type(e).__name__}: {e}')
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
    a = ap.parse_args()
    scores = json.load(open(a.scores))
    parts = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(a.stl_dir, '*.stl')))
    if a.parts:
        parts = [p for p in parts if any(p.startswith(q) for q in a.parts)]
    jobs = [(os.path.join(ROOT, 'bench', 'runs', r), p, os.path.join(a.stl_dir, p + '.stl'),
             bool(scores[r].get(p, {}).get('cad_valid')), a.n_cad) for r in a.runs for p in parts]
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

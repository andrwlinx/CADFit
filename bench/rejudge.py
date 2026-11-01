#!/usr/bin/env python3
"""
Independent higher-precision re-judge of score.py --cad results.

  python bench/rejudge.py --scores bench/runs/h2_scores.json --stl-dir bench/cadbench/fresh2 \
      --runs h2s0_v2 h2s0_v3 --jobs 16 --out bench/runs/h2_rejudge.json

Selection decisions stay fixed: the same executed STL (<recon>_cad.stl, written by
score.py's replay) is judged again. Parts the scores file judged exactly are copied
(the exact boolean has no sampling error); parts judged by the winding-number Monte
Carlo estimate are re-judged with an independent seed (1) and 4x the union samples
(min_union 40,000, up to 20 batches). Validity gating is unchanged.
"""
import argparse
import glob
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
RECON = ('best_greedy_parallel_iterative', 'best_greedy_parallel')


def one(job):
    run, part, gt, rec = job
    import score
    out = {'iou_cad_gated': rec.get('iou_cad_gated', 0.0), 'cad_valid': rec.get('cad_valid'),
           'method': (rec.get('cad_judge') or {}).get('method')}
    if not rec.get('cad_valid') or out['method'] == 'exact':
        return run, part, out
    stem = next((os.path.join(run, part, r) for r in RECON if os.path.exists(os.path.join(run, part, r + '.stl'))),
                None)
    stl = stem + '_cad.stl' if stem else None
    if not stl or not os.path.exists(stl):
        return run, part, {**out, 'error': 'executed STL missing'}
    j = score.robust_iou(gt, stl, seed=1, min_union=40000, max_batches=20)
    return run, part, {**out, 'iou_cad_gated': float(j['iou']), 'first_estimate': rec.get('iou_cad_gated'),
                       'rejudged': True, 'se': j.get('se'), 'union_samples': j.get('union_samples')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scores', required=True)
    ap.add_argument('--stl-dir', required=True)
    ap.add_argument('--runs', nargs='+', required=True)
    ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    scores = json.load(open(a.scores))
    root = os.path.join(os.path.dirname(HERE), 'bench', 'runs')
    jobs = [(os.path.join(root, r), p, os.path.join(a.stl_dir, p + '.stl'), scores[r][p] or {})
            for r in a.runs for p in sorted(scores[r])]
    out = {r: {} for r in a.runs}
    with ProcessPoolExecutor(a.jobs) as ex:
        for run, part, rec in ex.map(one, jobs):
            out[os.path.basename(run)][part] = rec
    json.dump(out, open(a.out, 'w'), indent=1)
    for r in a.runs:
        v = out[r].values()
        print(r, 'mean gated', round(sum(x['iou_cad_gated'] for x in v) / len(out[r]), 4),
              're-judged', sum(bool(x.get('rejudged')) for x in v))


if __name__ == '__main__':
    main()

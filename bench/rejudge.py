#!/usr/bin/env python3
"""
Independent higher-precision re-judge of the delivered CAD, selection fixed.

  python bench/rejudge.py --stl-dir bench/cadbench/fresh2 --manifest bench/cadbench/fresh2/manifest.json \
      --scores bench/runs/h2_scores.json --runs h2s0_v2 h2s0_v3 \
      --trim h2s0_v3trim=bench/runs/h2s0_v3_trim.json --jobs 16 --out bench/runs/h2_rejudge.json

What is judged is what the arm delivered, never reselected:
  --runs  (score.py --cad records): the run's replayed program, <recon>_cad.stl;
  --trim  name=trim.json (bench/analysis/trim_posthoc.py): the selected variant's
          executed tessellation (its 'stl', else <run>/<part>/trim_posthoc/exec_<chosen>.stl),
          whether that is the trimmed program or the retained original.
Every validly delivered part is judged again by score.robust_iou with an independent
seed (1) and 4x the union samples (min_union 40,000, up to 20 batches); the exact
boolean path, where it applies, gives the same value as before (no sampling error).
Invalid or missing deliveries stay 0. Every part of --manifest must have a record,
or the run is reported incomplete instead of being scored.
"""
import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
RUNS = os.path.join(ROOT, 'bench', 'runs')
RECON = ('best_greedy_parallel_iterative', 'best_greedy_parallel')


def run_stl(run, part):
    stem = next((os.path.join(RUNS, run, part, r) for r in RECON
                 if os.path.exists(os.path.join(RUNS, run, part, r + '.stl'))), None)
    return stem + '_cad.stl' if stem else None


def trim_stl(run, part, rec):
    if rec.get('stl'):
        return rec['stl']
    return os.path.join(RUNS, run, part, 'trim_posthoc', f"exec_{rec['chosen']}.stl") if rec.get('chosen') else None


def one(job):
    name, part, gt, valid, first, stl = job
    out = {'valid': valid, 'first_estimate': first, 'iou_cad_gated': 0.0}
    if not valid:
        return name, part, out
    if not stl or not os.path.exists(stl):
        return name, part, {**out, 'error': f'delivered STL missing: {stl}'}
    # Per-part result cache next to the delivered STL (I/O only, values unchanged): a job stopped
    # at its time limit resumes. Valid while the STL is not newer than the cache.
    cache = stl + '.rejudge_s1.json'
    if os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(stl):
        return name, part, {**out, **json.load(open(cache))}
    import score
    j = score.robust_iou(gt, stl, seed=1, min_union=40000, max_batches=20)
    rec = {'iou_cad_gated': float(j['iou']), 'method': j.get('method'), 'se': j.get('se'),
           'union_samples': j.get('union_samples'), 'stl': stl}
    tmp = f'{cache}.{os.getpid()}'
    json.dump(rec, open(tmp, 'w'))
    os.replace(tmp, cache)
    return name, part, {**out, **rec}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stl-dir', required=True)
    ap.add_argument('--manifest', required=True, help='cohort manifest (every part must have a record)')
    ap.add_argument('--scores', help='score.py --cad output holding the --runs')
    ap.add_argument('--runs', nargs='*', default=[])
    ap.add_argument('--trim', nargs='*', default=[], help='name=trim_posthoc output; the run is the json stem')
    ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    parts = sorted(m['file_id'] for m in json.load(open(a.manifest)))
    jobs, incomplete = [], {}
    scores = json.load(open(a.scores)) if a.runs else {}
    for r in a.runs:
        res = scores.get(r, {})
        miss = [p for p in parts if p not in res]
        if miss:
            incomplete[r] = miss
            continue
        for p in parts:
            rec = res[p] or {}
            jobs.append((r, p, os.path.join(a.stl_dir, p + '.stl'), bool(rec.get('cad_valid')),
                         rec.get('iou_cad_gated', 0.0), run_stl(r, p)))
    for spec in a.trim:
        name, path = spec.split('=')
        res = json.load(open(path))
        run = os.path.basename(path)[:-len('_trim.json')]
        miss = [p for p in parts if p not in res]
        if miss:
            incomplete[name] = miss
            continue
        for p in parts:
            rec = res[p]
            ok = rec.get('status') == 'ok' and bool(rec.get('chosen_valid'))
            jobs.append((name, p, os.path.join(a.stl_dir, p + '.stl'), ok, rec.get('gated', 0.0),
                         trim_stl(run, p, rec) if ok else None))
    out = {'incomplete': incomplete}
    with ProcessPoolExecutor(a.jobs) as ex:
        for name, part, rec in ex.map(one, jobs):
            out.setdefault(name, {})[part] = rec
    json.dump(out, open(a.out, 'w'), indent=1)
    for name, res in out.items():
        if name == 'incomplete':
            continue
        v = list(res.values())
        print(f"{name:<16} first {sum(x['first_estimate'] or 0 for x in v) / len(v):.4f}  "
              f"rejudged {sum(x['iou_cad_gated'] for x in v) / len(v):.4f}  n={len(v)}  "
              f"errors {sum('error' in x for x in v)}")
    for name, miss in incomplete.items():
        print(f'INCOMPLETE {name}: {len(miss)} manifest parts without a record')


if __name__ == '__main__':
    main()

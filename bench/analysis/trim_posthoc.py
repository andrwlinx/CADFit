#!/usr/bin/env python3
"""
Silhouette trim applied after the fact to a run's delivered programs.

  python bench/analysis/trim_posthoc.py bench/runs/dev6_v3 bench/cadbench/fresh --jobs 16 \
      --out bench/runs/dev6_v3_trim.json

The trim is the last stage of exec-verify (exec_verify.verify(trim=True)), after
the search, so running it on the program a run delivered gives exactly what that
run would have delivered with the trim on: the delivered program and its
silhouette-trimmed copy are both executed and judged, and the better valid one is
kept. Per part: the delivered program's executed record, the trim's, and the
choice, in the format of exec_verify.
"""
import argparse
import glob
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
RECON = ('best_greedy_parallel_iterative.py', 'best_greedy_parallel.py')


def one(job):
    run, part, target = job
    import exec_verify
    prog = next((os.path.join(run, part, r) for r in RECON if os.path.exists(os.path.join(run, part, r))), None)
    if prog is None:
        return part, {'status': 'no_program'}
    out = os.path.join(run, part, 'trim_posthoc')
    try:
        rec = exec_verify.verify(prog, target, out, trim=True)
    except Exception as e:  # noqa: BLE001
        return part, {'status': f'error: {type(e).__name__}: {e}'}
    v = rec['variants']
    trim = next((k for k in v if k.endswith('_trim')), None)
    # The same choice without the trimmed variant: the difference is the trim alone.
    base = {k: r for k, r in v.items() if k != trim and 'same_program_as' not in r}
    k0 = exec_verify.choose(base)
    gated0 = base[k0]['iou_exec'] if k0 and base[k0].get('valid') else 0.0
    return part, {'status': 'ok', 'chosen': rec['chosen'], 'chosen_valid': rec['chosen_valid'],
                  'gated': rec['validity_gated_iou'], 'gated_no_trim': gated0, 'trim': trim,
                  'trim_record': v.get(trim), 'original': v.get('original')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('run')
    ap.add_argument('stl_dir')
    ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    parts = sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(a.stl_dir, '*.stl')))
    jobs = [(a.run, p, os.path.join(a.stl_dir, p + '.stl')) for p in parts]
    res = {}
    with ProcessPoolExecutor(a.jobs) as ex:
        for part, r in ex.map(one, jobs):
            res[part] = r
            t = r.get('trim_record') or {}
            print(part[:8], r['status'], r.get('chosen'), round(r.get('gated', 0), 4),
                  'trim', t.get('valid'), round(t.get('iou_exec', 0) or 0, 4), flush=True)
    json.dump(res, open(a.out, 'w'), indent=1)
    ok = [r for r in res.values() if r['status'] == 'ok']
    print('trim chosen on', sum(bool(r['chosen'] and r['chosen'].endswith('_trim')) for r in ok), 'of', len(ok))
    n = len(parts)
    print(f"mean gated over {n} parts: no trim {sum(r.get('gated_no_trim', 0) for r in res.values()) / n:.4f}, "
          f"with trim {sum(r.get('gated', 0) for r in res.values()) / n:.4f}")


if __name__ == '__main__':
    main()

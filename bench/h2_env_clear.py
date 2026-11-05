#!/usr/bin/env python3
"""Clear the cached replay record and score of every held-out part whose CAD replay
failed for a machine reason (score.env_failure: sandbox setup, rc -9, timeout), in
every run alike, so `h2_post.sh score1 <run>` judges those programs again.

  python3 bench/h2_env_clear.py bench/runs h2s0_d0 h2s0_dx ... [--dry-run]

Prints, per run, how many parts were cleared and why; writes the list next to the
score files as h2_env_cleared.json (appended per invocation) for the record.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from score import env_failure  # noqa: E402

RECON = 'best_greedy_parallel_iterative'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('runs_dir')
    ap.add_argument('runs', nargs='+')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    log = {'time': time.strftime('%Y-%m-%dT%H:%M:%S'), 'dry_run': a.dry_run, 'runs': {}}
    for run in a.runs:
        scores = json.load(open(os.path.join(a.runs_dir, f'h2_scores_{run}.json')))[run]
        hit = {p: r.get('cad_error') for p, r in scores.items() if env_failure(r.get('cad_error'))}
        for p in hit:
            base = os.path.join(a.runs_dir, run, p, RECON)
            for suffix in ('_cad.json', '_cad.stl', '_score_robust_cad.json'):
                if os.path.exists(base + suffix) and not a.dry_run:
                    os.remove(base + suffix)
        kinds = {}
        for e in hit.values():
            k = 'timeout' if e.startswith('timeout') else 'sandbox' if 'ns_sandbox' in e else 'killed'
            kinds[k] = kinds.get(k, 0) + 1
        print(f'{run}: {len(hit)} cleared {kinds}')
        log['runs'][run] = {'cleared': sorted(hit), 'kinds': kinds}
    if not a.dry_run:
        path = os.path.join(a.runs_dir, 'h2_env_cleared.json')
        prev = json.load(open(path)) if os.path.exists(path) else []
        json.dump(prev + [log], open(path, 'w'), indent=1)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Compare two full-pipeline runs (run_pipeline.py with CADFIT_PROFILE set).

Reports per-step wall totals from the profiles, per-part durations, sleep
taint (zero-event holes), and strict-judge IoU (bench/score.py) of the final
reconstruction of every part.

Usage:
  python bench/full_compare.py --base bench/runs/base2 --new bench/runs/full_all \
      --stl-dir bench/synthetic [--out summary.json]
Each run folder must hold profile.jsonl and stock_synth/<part>/.
"""
import argparse
import collections
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from score import strict_iou  # noqa: E402


def load_profile(path):
    parts, steps, phases = {}, collections.defaultdict(float), collections.defaultdict(float)
    cur, ts = None, []
    for line in open(path):
        e = json.loads(line)
        ts.append(e['t'])
        k = e['kind']
        if k == 'stl_start':
            cur = os.path.splitext(os.path.basename(e['stl']))[0]
            parts[cur] = {'steps': collections.defaultdict(float), 'gap': 0.0, 'last_t': e['t']}
        elif cur is None:
            continue
        else:
            p = parts[cur]
            p['gap'] = max(p['gap'], e['t'] - p['last_t'])
            p['last_t'] = e['t']
            if k == 'step':
                steps[e['step']] += e['duration']
                p['steps'][e['step']] += e['duration']
            elif k == 'prune_phase':
                phases[e['phase']] += e['duration']
            elif k == 'evaluate':
                phases['evaluate'] += e['duration']
            elif k == 'stl_done':
                p['duration'] = e['duration']
                p['final_iou'] = e['final_iou']
    return parts, steps, phases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--new', required=True)
    ap.add_argument('--stl-dir', required=True)
    ap.add_argument('--out')
    ap.add_argument('--gap', type=float, default=600.0,
                    help='zero-event hole (s) inside a part that marks it as slept; translation analysis '
                         'emits no events, so keep this above its longest legitimate run')
    args = ap.parse_args()

    runs = {}
    for name, folder in (('base', args.base), ('new', args.new)):
        parts, steps, phases = load_profile(os.path.join(folder, 'profile.jsonl'))
        for part, p in parts.items():
            recon = os.path.join(folder, 'stock_synth', part, 'best_greedy_parallel_iterative.stl')
            gt = os.path.join(args.stl_dir, part + '.stl')
            p['strict'] = strict_iou(gt, recon) if os.path.exists(recon) else None
            p['tainted'] = p['gap'] > args.gap
        runs[name] = {'parts': parts, 'steps': dict(steps), 'phases': dict(phases)}

    common = sorted(set(runs['base']['parts']) & set(runs['new']['parts']))
    clean = [p for p in common if not (runs['base']['parts'][p]['tainted'] or runs['new']['parts'][p]['tainted'])]
    print(f"parts: {len(common)} common, {len(clean)} untainted")

    def tot(name, key, sel):
        return sum(runs[name]['parts'][p]['steps'].get(key, 0.0) for p in sel)
    print(f"\n{'step':<32} {'base':>8} {'new':>8} {'ratio':>6}   (untainted parts only)")
    for key in sorted(runs['base']['steps'], key=lambda k: -runs['base']['steps'][k]):
        b, n = tot('base', key, clean), tot('new', key, clean)
        print(f"{key:<32} {b:>8.0f} {n:>8.0f} {n / b if b else 0:>6.2f}")
    b = sum(runs['base']['parts'][p].get('duration', 0) for p in clean)
    n = sum(runs['new']['parts'][p].get('duration', 0) for p in clean)
    print(f"{'TOTAL':<32} {b:>8.0f} {n:>8.0f} {n / b if b else 0:>6.2f}")

    print(f"\n{'part':<22} {'base IoU':>9} {'new IoU':>9} {'delta':>8} {'base s':>7} {'new s':>7}  taint")
    d = []
    for p in common:
        rb, rn = runs['base']['parts'][p], runs['new']['parts'][p]
        ib = rb['strict']['iou'] if rb['strict'] else float('nan')
        inn = rn['strict']['iou'] if rn['strict'] else float('nan')
        d.append(inn - ib)
        print(f"{p:<22} {ib:>9.4f} {inn:>9.4f} {inn - ib:>+8.4f} {rb.get('duration', 0):>7.0f} {rn.get('duration', 0):>7.0f}  "
              f"{'B' if rb['tainted'] else ''}{'N' if rn['tainted'] else ''}")
    d = np.array(d)
    rng = np.random.default_rng(0)
    ci = np.percentile(rng.choice(d, (5000, len(d))).mean(1), [2.5, 97.5])
    print(f"\nstrict IoU: base mean {np.nanmean([runs['base']['parts'][p]['strict']['iou'] for p in common]):.4f}  "
          f"new mean {np.nanmean([runs['new']['parts'][p]['strict']['iou'] for p in common]):.4f}  "
          f"mean delta {d.mean():+.4f} (95% CI {ci[0]:+.4f}..{ci[1]:+.4f})  worst {d.min():+.4f}  "
          f"improved {int((d > 0.005).sum())}  regressed {int((d < -0.005).sum())}")
    if args.out:
        json.dump(runs, open(args.out, 'w'), indent=1, default=float)


if __name__ == '__main__':
    main()

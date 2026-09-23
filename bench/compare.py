#!/usr/bin/env python3
"""
Compare greedy-search arms produced by bench/run_arms.sh against the `stock` arm.

Per arm and STL it reads: done (wall time, exit code), log.txt (final IoU),
greedy_extrusion_data.json (selected operations) and profile.jsonl (phase
durations, CadQuery launches, IoU calls). Reports paired deltas vs stock.

Usage: python bench/compare.py bench/runs/arms [--out summary.json]
"""
import argparse
import glob
import hashlib
import json
import os
import re

import numpy as np


def load_run(folder):
    done = json.load(open(os.path.join(folder, 'done')))
    out = {'wall': done['wall'], 'exit': done['exit'], 'final_iou': None, 'selected': None,
           'cq_exec': 0, 'iou_calls': 0, 'phases': {}, 'n_in': None, 'n_eval': None}
    log = open(os.path.join(folder, 'log.txt'), errors='replace').read()
    m = re.findall(r'^Final IoU: ([0-9.]+)', log, flags=re.M)
    if m:
        out['final_iou'] = float(m[-1])
    # Signature of the greedy result. The stock 'selected' flags in
    # greedy_extrusion_data.json are always False, so use the final generated
    # scripts (output paths stripped) plus the greedy path counts from the log.
    sig = []
    for sp in sorted(glob.glob(os.path.join(folder, 'greedy_tmp_*.py'))):
        text = re.sub(r"['\"][^'\"]*\.stl['\"]", "'OUT.stl'", open(sp).read())
        sig.append((os.path.basename(sp), hashlib.md5(text.encode()).hexdigest()))
    path = re.findall(r'Selected (\d+) out of (\d+)|removed (\d+) out of (\d+)', log)
    greedy_iou = re.findall(r'Final IoU after post-processing: ([0-9.]+)', log)
    out['selected'] = [sig, path, greedy_iou[-1:] ]
    out['n_ops'] = sum(open(sp).read().count('.extrude(') + open(sp).read().count('.revolve(')
                       for sp in glob.glob(os.path.join(folder, 'greedy_tmp_*.py')))
    out['single_fallback'] = 'using individual instead' in log
    p = os.path.join(folder, 'profile.jsonl')
    if os.path.exists(p):
        # A zero-event hole longer than any single CadQuery/IoU call should be
        # means the machine slept; wall time for this run is then not trustworthy.
        ts = []
        for line in open(p):
            e = json.loads(line)
            ts.append(e['t'])
            if e['kind'] == 'cq_exec':
                out['cq_exec'] += 1
            elif e['kind'] == 'iou':
                out['iou_calls'] += 1
            elif e['kind'] == 'evaluate':
                out['phases']['evaluate'] = e['duration']
                out['n_eval'] = e['n']
            elif e['kind'] == 'ranking':
                out['phases']['ranking'] = e['duration']
                out['n_in'] = e['n_in']
            elif e['kind'] == 'prune_phase':
                out['phases'][e['phase']] = e['duration']
            elif e['kind'] == 'solid_cache':
                out['solid_cache_hits'] = out.get('solid_cache_hits', 0) + int(bool(e.get('hit')))
        ts.sort()
        out['max_gap'] = max((b - a for a, b in zip(ts, ts[1:])), default=0.0)
        if ts:
            # Sleep before the first / after the last event shows up as wall
            # time not covered by the event span (plus interpreter start-up).
            out['outside_span'] = out['wall'] - (ts[-1] - ts[0])
    # Interpreter start-up plus final writes is ~5-20 s; anything beyond that,
    # or any zero-event hole longer than a CadQuery call, means the machine
    # was asleep or starved.
    out['tainted'] = out.get('max_gap', 0.0) > 60.0 or out.get('outside_span', 0.0) > 45.0
    return out


def bootstrap_ci(x, n=5000, seed=0):
    x = np.asarray(x, dtype=float)
    if len(x) < 2:
        return None
    rng = np.random.default_rng(seed)
    means = rng.choice(x, size=(n, len(x)), replace=True).mean(axis=1)
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def main():
    ap = argparse.ArgumentParser(description='Compare greedy-search arms against stock')
    ap.add_argument('arms_dir')
    ap.add_argument('--out', default=None)
    ap.add_argument('--base', default='stock', help='arm to compare against (default: stock)')
    ap.add_argument('--scores', default=None, help='bench/score.py --out file; if given, IoU columns use it')
    args = ap.parse_args()
    scores = json.load(open(args.scores)) if args.scores else None

    runs = {}
    for done in glob.glob(os.path.join(args.arms_dir, '*', '*', 'done')):
        folder = os.path.dirname(done)
        arm, stl = folder.split(os.sep)[-2:]
        runs.setdefault(arm, {})[stl] = load_run(folder)
    # Relative taint: dead time (outside the event span) far above the same
    # part's median across arms means that run was slept or starved.
    parts = {stl for by_stl in runs.values() for stl in by_stl}
    for stl in parts:
        vals = [runs[a][stl].get('outside_span', 0.0) for a in runs if stl in runs[a]]
        med = float(np.median(vals)) if vals else 0.0
        for a in runs:
            if stl in runs[a] and runs[a][stl].get('outside_span', 0.0) > max(15.0, 2.5 * med):
                runs[a][stl]['tainted'] = True

    base = args.base
    if base not in runs:
        raise SystemExit(f'no {base} arm found')
    if scores:
        for arm, by_stl in runs.items():
            for stl, r in by_stl.items():
                sc = scores.get(arm, {}).get(stl)
                r['final_iou'] = None if sc is None else sc['iou']

    summary = {}
    for arm, by_stl in sorted(runs.items()):
        ids = sorted(set(by_stl) & set(runs[base]))
        rows = [(by_stl[i], runs[base][i]) for i in ids]
        ok = [(a, s) for a, s in rows if a['final_iou'] is not None and s['final_iou'] is not None]
        d_iou = [a['final_iou'] - s['final_iou'] for a, s in ok]
        phases = sorted({k for a, _ in rows for k in a['phases']})
        summary[arm] = {
            'n': len(ids),
            'failures': sum(a['exit'] != 0 or a['final_iou'] is None for a, _ in rows),
            'mean_iou': float(np.mean([a['final_iou'] for a, _ in ok])) if ok else None,
            'mean_d_iou': float(np.mean(d_iou)) if ok else None,
            'd_iou_ci95': bootstrap_ci(d_iou) if ok else None,
            'worst_d_iou': float(min(d_iou)) if ok else None,
            'identical_selection': sum(a['selected'] == s['selected'] for a, s in rows),
            'wall_total': sum(a['wall'] for a, _ in rows),
            # Wall ratio over pairs where neither run slept.
            'wall_ratio_vs_stock': (sum(a['wall'] for a, s in rows if not (a['tainted'] or s['tainted'])) /
                                    max(1, sum(s['wall'] for a, s in rows if not (a['tainted'] or s['tainted'])))),
            'tainted': sum(a['tainted'] or s['tainted'] for a, s in rows),
            'solid_cache_hits': sum(a.get('solid_cache_hits', 0) for a, _ in rows),
            'cq_exec_total': sum(a['cq_exec'] for a, _ in rows),
            'iou_calls_total': sum(a['iou_calls'] for a, _ in rows),
            'n_ops_mean': float(np.mean([a['n_ops'] for a, _ in rows])),
            'single_fallback': sum(a['single_fallback'] for a, _ in rows),
            'phase_totals': {k: round(sum(a['phases'].get(k, 0.0) for a, _ in rows), 1) for k in phases},
        }

    hdr = f"{'arm':<13} {'n':>3} {'fail':>4} {'IoU':>7} {'dIoU':>8} {'worst':>8} {'same':>5} {'wall':>7} {'x base':>7} {'taint':>5} {'cq':>6} {'iou':>6}  phases"
    print(hdr)
    for arm, s in summary.items():
        f = lambda v, spec: '-' if v is None else format(v, spec)
        print(f"{arm:<13} {s['n']:>3} {s['failures']:>4} {f(s['mean_iou'], '.4f'):>7} {f(s['mean_d_iou'], '+.4f'):>8} "
              f"{f(s['worst_d_iou'], '+.4f'):>8} {s['identical_selection']:>5} {s['wall_total']:>7} "
              f"{s['wall_ratio_vs_stock']:>7.2f} {s['tainted']:>5} {s['cq_exec_total']:>6} {s['iou_calls_total']:>6}  {s['phase_totals']}")

    if args.out:
        with open(args.out, 'w') as f:
            json.dump({'summary': summary, 'runs': runs}, f, indent=2)


if __name__ == '__main__':
    main()

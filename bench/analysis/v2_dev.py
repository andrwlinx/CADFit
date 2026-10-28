#!/usr/bin/env python3
"""
Dev-cohort analysis of the CADFit++ v2 arms (60 parts, bench/cadbench/fresh).

  python3 bench/analysis/v2_dev.py results/dev345_scores.json [results/dev6_scores.json ...] \
      --pairs dev5_dx:dev5_d0 dev5_v2:dev5_d0 dev5_v2:dev5_dx dev6_v3:dev6_v2 --out results/v2_dev.json

Every cohort part counts: a part a run did not score (no model, never ran) is 0.
Primary metric: validity-gated CAD IoU (iou_cad_gated). For each run: mean over
all parts, the benchA / benchE split means and their balanced average, valid
deliveries. For each pair a-b: mean paired difference with a split-stratified
paired bootstrap CI (parts resampled within their split, 10,000 resamples,
seed 0), wins/losses (|d| > 0.005), a two-sided sign test, Holm-adjusted over
the pairs given (the Holm adjustment is for the sign tests, not the intervals),
and the share of the difference from parts b did not deliver valid CAD.
Repeats (--avg) are averaged within part before pairing, so parts stay the
resampling unit.
"""
import argparse
import json
import math
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def cohort():
    man = json.load(open(os.path.join(ROOT, 'bench', 'cadbench', 'fresh', 'manifest.json')))
    return {m['file_id']: m['split'] for m in man}


def gated(rec):
    return float((rec or {}).get('iou_cad_gated') or 0.0)


def valid(rec):
    return bool((rec or {}).get('cad_valid'))


def sign_p(w, l):
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def boot(d, split, n=10000, seed=0, alpha=0.05):
    groups = {}
    for p, x in d.items():
        groups.setdefault(split[p], []).append(x)
    r = random.Random(seed)
    stats = []
    for _ in range(n):
        tot = cnt = 0
        for g in groups.values():
            s = [g[r.randrange(len(g))] for _ in g]
            tot += sum(s)
            cnt += len(s)
        stats.append(tot / cnt)
    stats.sort()
    return stats[int(alpha / 2 * n)], stats[int((1 - alpha / 2) * n) - 1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('scores', nargs='+')
    ap.add_argument('--pairs', nargs='*', default=[])
    ap.add_argument('--avg', nargs='*', default=[],
                    help='name=run1,run2,...: a run whose per-part gated IoU is the mean over repeats '
                         '(cad_valid when valid in every repeat); pairs then use name')
    ap.add_argument('--out')
    a = ap.parse_args()
    split = cohort()
    parts = sorted(split)
    runs = {}
    for f in a.scores:
        runs.update(json.load(open(f)))
    for spec in a.avg:
        name, members = spec.split('=')
        members = members.split(',')
        runs[name] = {p: {'iou_cad_gated': sum(gated(runs[m].get(p)) for m in members) / len(members),
                          'cad_valid': all(valid(runs[m].get(p)) for m in members)} for p in parts}
    out = {'n_parts': len(parts), 'runs': {}, 'pairs': {}}
    for name, res in runs.items():
        v = {p: gated(res.get(p)) for p in parts}
        by = {s: [v[p] for p in parts if split[p] == s] for s in ('benchA', 'benchE')}
        missing = [p for p in parts if res.get(p) is None or res[p].get('status') in ('no_model', 'not_run')]
        out['runs'][name] = {
            'mean_gated': sum(v.values()) / len(parts),
            'benchA': sum(by['benchA']) / len(by['benchA']), 'benchE': sum(by['benchE']) / len(by['benchE']),
            'balanced': (sum(by['benchA']) / len(by['benchA']) + sum(by['benchE']) / len(by['benchE'])) / 2,
            'valid': sum(valid(res.get(p)) for p in parts), 'missing': missing}
    raw = []
    for pr in a.pairs:
        x, y = pr.split(':')
        d = {p: gated(runs[x].get(p)) - gated(runs[y].get(p)) for p in parts}
        lo, hi = boot(d, split)
        w = sum(v > 0.005 for v in d.values())
        l = sum(v < -0.005 for v in d.values())
        tot = sum(d.values())
        from_invalid = sum(d[p] for p in parts if not valid(runs[y].get(p)))
        rec = {'diff': tot / len(parts), 'ci95': [lo, hi], 'wins': w, 'losses': l, 'sign_p': sign_p(w, l),
               'share_from_b_invalid': from_invalid / tot if tot else None,
               'both_valid_diff': (lambda q: sum(d[p] for p in q) / len(q) if q else None)(
                   [p for p in parts if valid(runs[x].get(p)) and valid(runs[y].get(p))])}
        out['pairs'][pr] = rec
        raw.append((pr, rec['sign_p']))
    # Holm over the pairs given (the prespecified family).
    m = len(raw)
    running = 0.0
    for i, (pr, p) in enumerate(sorted(raw, key=lambda t: t[1])):
        running = max(running, min(1.0, (m - i) * p))
        out['pairs'][pr]['sign_p_holm'] = running
    for name, r in out['runs'].items():
        print(f"{name:<12} gated {r['mean_gated']:.4f}  A {r['benchA']:.4f}  E {r['benchE']:.4f}  "
              f"valid {r['valid']}/{len(parts)}  missing {len(r['missing'])}")
    for pr, r in out['pairs'].items():
        print(f"{pr:<22} {r['diff']:+.4f} [{r['ci95'][0]:+.4f}, {r['ci95'][1]:+.4f}]  {r['wins']}/{r['losses']}  "
              f"p_holm {r['sign_p_holm']:.4f}  from-invalid {r['share_from_b_invalid']}  "
              f"both-valid {r['both_valid_diff']}")
    if a.out:
        json.dump(out, open(a.out, 'w'), indent=1)


if __name__ == '__main__':
    main()

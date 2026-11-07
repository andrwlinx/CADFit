"""Tools-v3 study analysis, exactly as review-stage/TOOLS_V3_PROTOCOL.md declares it.

Inputs: bench/agentsk_score.py outputs tv_<v2|v3>_<r0|r1|r2>_scores.json (every delivered
program re-judged with score.py's CAD replay on the 40 fresh3 parts) and the episodes'
result.json files under the run folders tv_<version>_<rep>/.
Endpoint: iou_cad_gated, a missing delivery 0, repeats averaged within part.
Primary: Opus skills v3 - Opus skills v2. Secondary: Opus skills v3 - Opus code v3,
Opus code v3 - Opus code v2, the same three for Sonnet. Paired bootstrap over parts within
split (95%); Holm over the sign tests of the three Opus comparisons.

  .venv/bin/python bench/analysis/tools_v3.py --scores results/tools_v3 --episodes results/tools_v3/episodes \
      --out results/tools_v3/tools_v3.json
"""
import argparse
import json
import math
import os
import random
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPS = ('r0', 'r1', 'r2')
MODELS = ('opus55', 'sonnet55')


def boot(d, split, parts, n=10000, seed=0):
    rng = random.Random(seed)
    groups = [[d[p] for p in parts if split[p] == s] for s in sorted(set(split.values()))]
    m = sorted(sum(sum(rng.choices(g, k=len(g))) for g in groups) / len(parts) for _ in range(n))
    return m[int(0.025 * n)], m[int(0.975 * n)]


def sign_p(d):
    """Two-sided exact sign test over nonzero per-part differences."""
    pos, neg = sum(v > 1e-9 for v in d), sum(v < -1e-9 for v in d)
    n, k = pos + neg, min(pos, neg)
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, run = [0.0] * len(ps), 0.0
    for r, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - r) * ps[i]))
        adj[i] = run
    return adj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scores', required=True, help='folder with tv_<version>_<rep>_scores.json')
    ap.add_argument('--episodes', default=None, help='folder holding tv_<version>_<rep>/<model>/<toolset>/<part>/result.json')
    ap.add_argument('--out')
    a = ap.parse_args()
    sub = json.load(open(os.path.join(ROOT, 'bench', 'cadbench', 'fresh3_parts.json')))['parts']
    split = {p: k for k, v in sub.items() for p in v}
    parts = sorted(split)
    cells, detail = {}, {}
    for v in ('v2', 'v3'):
        reps = [json.load(open(os.path.join(a.scores, f'tv_{v}_{r}_scores.json')))['conditions'] for r in REPS]
        for m in MODELS:
            for t in ('code', 'skills'):
                c = f'{m}/{t}'
                assert all(set(r[c]) >= set(parts) for r in reps), f'{v} {c}: parts missing'
                key = f'{m}/{t}/{v}'
                cells[key] = {p: st.mean(r[c][p].get('iou_cad_gated', 0.0) for r in reps) for p in parts}
                eps = [r[c][p] for r in reps for p in parts]
                d = {'episodes': len(eps), 'delivered_valid': sum(bool(x.get('cad_valid')) for x in eps),
                     'verified_in_episode': sum(bool(x.get('verified_in_episode')) for x in eps),
                     'no_output': sum(not x.get('cad_built') for x in eps),
                     'stop': {s: sum(x.get('stop') == s for x in eps) for s in sorted({str(x.get('stop')) for x in eps})},
                     'mean_s': st.mean(x['seconds'] for x in eps if x.get('seconds') is not None),
                     'median_s': st.median(x['seconds'] for x in eps if x.get('seconds') is not None),
                     'cost_total': sum(x.get('cost_usd') or 0 for x in eps),
                     'repeat_means': [st.mean(r[c][p].get('iou_cad_gated', 0.0) for p in parts) for r in reps]}
                if a.episodes:  # model vs tool time and unchecked steps from the episode records
                    rs = []
                    for r in REPS:
                        for p in parts:
                            f = os.path.join(a.episodes, f'tv_{v}_{r}', m, t, p, 'result.json')
                            if os.path.exists(f):
                                rs.append(json.load(open(f)))
                    tot = sum(sum(x['seconds_split'].values()) for x in rs) or 1
                    d['model_time_share'] = sum(x['seconds_split']['model'] for x in rs) / tot
                detail[key] = d
    out = {'parts': parts, 'split': split, 'cells': {}, 'detail': detail, 'comparisons': {}}
    for k, d in cells.items():
        out['cells'][k] = {s: st.mean(d[p] for p in parts if s == 'all' or split[p] == s) for s in ('benchA', 'benchE', 'all')}
        out['cells'][k]['ci95'] = boot(d, split, parts)
    comps = []
    for m in MODELS:
        comps += [(m, 'primary' if m == 'opus55' else 'secondary', f'{m}/skills/v3', f'{m}/skills/v2'),
                  (m, 'secondary', f'{m}/skills/v3', f'{m}/code/v3'),
                  (m, 'secondary', f'{m}/code/v3', f'{m}/code/v2')]
    for m, role, x, y in comps:
        dd = {p: cells[x][p] - cells[y][p] for p in parts}
        out['comparisons'][f'{x} - {y}'] = {'model': m, 'role': role, 'mean': st.mean(dd.values()),
                                            'ci95': boot(dd, split, parts), 'sign_p': sign_p(list(dd.values())),
                                            'wins': sum(v > 1e-9 for v in dd.values()),
                                            'losses': sum(v < -1e-9 for v in dd.values())}
    opus = [k for k, v in out['comparisons'].items() if v['model'] == 'opus55']
    for k, p in zip(opus, holm([out['comparisons'][k]['sign_p'] for k in opus])):
        out['comparisons'][k]['holm_p'] = p

    for k, r in out['cells'].items():
        d = detail[k]
        print(f'{k:22s} all {r["all"]:.4f} [{r["ci95"][0]:.4f}, {r["ci95"][1]:.4f}]  A {r["benchA"]:.4f} E {r["benchE"]:.4f}  '
              f'valid {d["delivered_valid"]}/{d["episodes"]}  no-output {d["no_output"]}  mean {d["mean_s"] / 60:.1f} min  '
              f'median {d["median_s"] / 60:.1f} min  ${d["cost_total"]:.2f}')
    for k, c in out['comparisons'].items():
        print(f'{c["role"]:9s} {k:40s} {c["mean"]:+.4f} [{c["ci95"][0]:+.4f}, {c["ci95"][1]:+.4f}]  W/L {c["wins"]}/{c["losses"]}  '
              f'sign p {c["sign_p"]:.3f}' + (f'  Holm {c["holm_p"]:.3f}' if 'holm_p' in c else ''))
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        json.dump(out, open(a.out, 'w'), indent=1)


if __name__ == '__main__':
    main()

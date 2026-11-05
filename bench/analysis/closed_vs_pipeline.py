"""Closed-model agents vs the CadFit pipeline on the 40 reserved fresh2 parts (exploratory,
not part of HELDOUT_PROTOCOL.md's preregistered contrasts).

Agents: bench/runs/agentsk_f2/<model>/<toolset>/<part>/result.json, one episode per part;
value = best_exec_iou if best_exec_valid else 0 (the executed program the agent delivers,
scored by the robust judge inside the harness). Pipeline: h2_scores_<run>.json iou_cad_gated
(score.py --cad); v2 and v3 averaged over seeds 0-2 within part; trim from the
trim_posthoc records that exist (seed-averaged over what is present).

  .venv/bin/python bench/analysis/closed_vs_pipeline.py results/review_bundle_2026-11-05 \
      --out results/closed_vs_pipeline.json
"""
import argparse
import glob
import json
import os
import random
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def boot(d, n=10000, seed=0):
    rng = random.Random(seed)
    m = [st.mean(rng.choices(d, k=len(d))) for _ in range(n)]
    m.sort()
    return m[int(0.025 * n)], m[int(0.975 * n)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('bundle')
    ap.add_argument('--out')
    a = ap.parse_args()
    sub = json.load(open(os.path.join(ROOT, 'bench', 'cadbench', 'fresh2_subset.json')))['parts']
    split = {p: k for k, v in sub.items() for p in v}
    parts = sorted(split)

    arms = {}
    for f in glob.glob(os.path.join(a.bundle, 'agentsk_f2', '*', '*', '*', 'result.json')):
        model, toolset, part = f.split(os.sep)[-4:-1]
        if model not in ('sonnet55', 'opus55'):
            continue  # opus55_node4002_failed: discarded node fault, kept on disk for the record
        r = json.load(open(f))
        arms.setdefault(f'{model}/{toolset}', {})[part] = {
            'v': r['best_exec_iou'] if r.get('best_exec_valid') else 0.0, 'harness_iou': r['best_iou'],
            'valid': bool(r.get('best_exec_valid')), 'seconds': r['seconds'], 'cost': r['cost_usd'], 'stop': r['stop']}

    def run(name):
        p = os.path.join(a.bundle, f'h2_scores_{name}.json')
        return json.load(open(p))[name] if os.path.exists(p) else None

    for arm, runs in {'pipe/d0': ['h2s0_d0'], 'pipe/dx': ['h2s0_dx'], 'pipe/v2x3': ['h2s0_v2', 'h2s1_v2', 'h2s2_v2'],
                      'pipe/v3x3': ['h2s0_v3', 'h2s1_v3', 'h2s2_v3']}.items():
        rs = [run(r) for r in runs]
        arms[arm] = {p: {'v': st.mean(r[p]['iou_cad_gated'] if p in r else 0.0 for r in rs),
                         'valid': all(p in r and r[p].get('cad_valid') for r in rs)} for p in parts}
    trims = [json.load(open(t)) for t in sorted(glob.glob(os.path.join(a.bundle, 'h2s*_v3_trim.json')))]
    if trims:
        arms[f'pipe/trim(x{len(trims)})'] = {p: {'v': st.mean(t[p]['gated'] if p in t else 0.0 for t in trims)}
                                            for p in parts}

    out = {'parts': parts, 'split': split, 'arms': {}, 'pairs': {}, 'all_agents_invalid': []}
    for name, d in arms.items():
        row = {}
        for s in ('benchA', 'benchE', 'all'):
            ps = [p for p in parts if s == 'all' or split[p] == s]
            vals = [d[p]['v'] for p in ps if p in d]
            row[s] = {'n': len(vals), 'mean': st.mean(vals), 'zeros': sum(v == 0 for v in vals)}
        if 'seconds' in next(iter(d.values())):
            row['all'].update(mean_s=st.mean(x['seconds'] for x in d.values()),
                              median_s=st.median(x['seconds'] for x in d.values()),
                              cost=sum(x['cost'] for x in d.values()),
                              budget_stops=sum(x['stop'] != 'finish' for x in d.values()))
        out['arms'][name] = row
    agents = [k for k in arms if not k.startswith('pipe/')]
    out['all_agents_invalid'] = [p for p in parts if all(not arms[k][p]['valid'] for k in agents)]
    ref = [k for k in arms if k.startswith('pipe/')]
    for x in agents + ['opus55/skills']:
        for y in ref + [k for k in agents if k != x]:
            if x == y or f'{y} - {x}' in out['pairs']:
                continue
            dd = [arms[x][p]['v'] - arms[y][p]['v'] for p in parts]
            lo, hi = boot(dd)
            out['pairs'][f'{x} - {y}'] = {'mean': st.mean(dd), 'ci95': [lo, hi],
                                          'wins': sum(v > 1e-9 for v in dd), 'losses': sum(v < -1e-9 for v in dd)}
    out['per_part'] = {p: {k: round(arms[k][p]['v'], 4) for k in arms} for p in parts}

    for k, r in out['arms'].items():
        a_ = r['all']
        extra = f"  mean {a_['mean_s']:.0f}s  ${a_['cost']:.2f}" if 'cost' in a_ else ''
        print(f"{k:18s} A {r['benchA']['mean']:.4f}  E {r['benchE']['mean']:.4f}  all {a_['mean']:.4f}  zeros {a_['zeros']}{extra}")
    for k, v in out['pairs'].items():
        if 'pipe/v3x3' in k or k.startswith('opus55/code - ') and not k.endswith('d0') and not k.endswith('dx'):
            print(f"{k:34s} {v['mean']:+.4f} [{v['ci95'][0]:+.4f}, {v['ci95'][1]:+.4f}]  W/L {v['wins']}/{v['losses']}")
    print('invalid in every agent arm:', out['all_agents_invalid'])
    if a.out:
        json.dump(out, open(a.out, 'w'), indent=1)


if __name__ == '__main__':
    main()

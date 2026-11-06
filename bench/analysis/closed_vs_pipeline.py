"""Closed-model agents vs the CadFit pipeline on the 40 reserved fresh2 parts (exploratory,
not part of HELDOUT_PROTOCOL.md's preregistered contrasts).

Agents (primary endpoint): every delivered program re-judged like the pipeline's
(bench/agentsk_score.py -> <tag>_scores.json, score.py CAD replay, iou_cad_gated); one file
per episode repeat, averaged within part. Also reported: whether the episode itself finished an
executed check of its answer (verified_in_episode) and, with --episodes, the episode's own
executed check of its best executed program (best_exec_iou if best_exec_valid, else 0).
Pipeline: h2_scores_<run>.json iou_cad_gated; v2 and v3 averaged over seeds 0-2 within part;
trim from the trim_posthoc records present. Uncertainty: paired bootstrap over parts,
resampled within split (20 benchA + 20 benchE).

  .venv/bin/python bench/analysis/closed_vs_pipeline.py --agents results/closed/agentsk_f2_scores.json \
      results/closed/agentsk_f2_r1_scores.json results/closed/agentsk_f2_r2_scores.json \
      --episodes results/review_bundle_2026-11-05/agentsk_f2{,_r1,_r2} \
      --pipeline results/review_bundle_2026-11-05 --out results/closed/closed_vs_pipeline.json
"""
import argparse
import glob
import json
import os
import random
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def boot(d, split, parts, n=10000, seed=0):
    """95% interval of the mean of per-part values d, parts resampled within split."""
    rng = random.Random(seed)
    groups = [[d[p] for p in parts if split[p] == s] for s in sorted(set(split.values()))]
    m = sorted(sum(sum(rng.choices(g, k=len(g))) for g in groups) / len(parts) for _ in range(n))
    return m[int(0.025 * n)], m[int(0.975 * n)]


def cause(r):
    if r.get('cad_valid'):
        return 'valid'
    e = str(r.get('cad_error') or '')
    if not r.get('cad_built') and ('no program' in e or not e and r.get('iou', 0) == 0):
        return 'no output'
    if e.startswith('timeout'):
        return 'execution timeout'
    if 'judge_error' in r:
        return 'judge failure'
    return 'invalid geometry'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--agents', nargs='+', required=True, help='agentsk_score.py outputs, one per repeat')
    ap.add_argument('--pipeline', required=True, help='folder with h2_scores_<run>.json and h2s*_v3_trim.json')
    ap.add_argument('--pipeline-runs', nargs='*', default=None,
                    help='arm=run,run,... (default: v3x3 and trim only, the runs without replay failures)')
    ap.add_argument('--episodes', nargs='*', default=[],
                    help='run folders <tag> holding <model>/<toolset>/<part>/result.json, same order as --agents')
    ap.add_argument('--out')
    a = ap.parse_args()
    sub = json.load(open(os.path.join(ROOT, 'bench', 'cadbench', 'fresh2_subset.json')))['parts']
    split = {p: k for k, v in sub.items() for p in v}
    parts = sorted(split)

    reps = [json.load(open(f))['conditions'] for f in a.agents]
    conds = sorted(reps[0])
    arms, detail = {}, {}
    for c in conds:
        per = {p: [r[c][p] for r in reps] for p in parts}
        arms[c] = {p: st.mean(x.get('iou_cad_gated', 0.0) for x in per[p]) for p in parts}
        if a.episodes:  # the episode's own executed check of its best executed program (not the mesh best)
            ex = {p: [] for p in parts}
            for tag in a.episodes:
                for p in parts:
                    f = os.path.join(tag, c, p, 'result.json')
                    r = json.load(open(f)) if os.path.exists(f) else {}
                    ex[p].append(r.get('best_exec_iou', 0.0) if r.get('best_exec_valid') else 0.0)
            arms[c + ' [in-episode check]'] = {p: st.mean(ex[p]) for p in parts}
        eps = [x for p in parts for x in per[p]]
        causes = {}
        for x in eps:
            causes[cause(x)] = causes.get(cause(x), 0) + 1
        detail[c] = {'episodes': len(eps), 'repeats': len(reps),
                     'delivered_valid': sum(bool(x.get('cad_valid')) for x in eps),
                     'verified_in_episode': sum(bool(x.get('verified_in_episode')) for x in eps),
                     'valid_but_unverified': sum(bool(x.get('cad_valid')) and not x.get('verified_in_episode')
                                                 for x in eps),
                     'causes': causes,
                     'stop': {s: sum(x.get('stop') == s for x in eps) for s in sorted({x.get('stop') for x in eps})},
                     'mean_s': st.mean(x['seconds'] for x in eps if x.get('seconds') is not None),
                     'median_s': st.median(x['seconds'] for x in eps if x.get('seconds') is not None),
                     'cost_per_episode': st.mean(x['cost_usd'] for x in eps if x.get('cost_usd') is not None),
                     'cost_total': sum(x['cost_usd'] for x in eps if x.get('cost_usd') is not None),
                     'repeat_means': [st.mean(r[c][p].get('iou_cad_gated', 0.0) for p in parts) for r in reps]}

    def run(name):
        return json.load(open(os.path.join(a.pipeline, f'h2_scores_{name}.json')))[name]

    specs = a.pipeline_runs or ['pipe/v3x3=h2s0_v3,h2s1_v3,h2s2_v3']
    for spec in specs:
        name, runs = spec.split('=')
        rs = [run(r) for r in runs.split(',')]
        arms[name] = {p: st.mean(r[p]['iou_cad_gated'] if p in r else 0.0 for r in rs) for p in parts}
    trims = [json.load(open(t)) for t in sorted(glob.glob(os.path.join(a.pipeline, 'h2s*_v3_trim.json')))]
    if trims:
        arms[f'pipe/trim(x{len(trims)})'] = {p: st.mean(t[p]['gated'] if p in t else 0.0 for t in trims)
                                            for p in parts}

    out = {'parts': parts, 'split': split, 'agents_files': a.agents, 'arms': {}, 'agent_detail': detail, 'pairs': {}}
    for name, d in arms.items():
        out['arms'][name] = {s: st.mean(d[p] for p in parts if s == 'all' or split[p] == s)
                             for s in ('benchA', 'benchE', 'all')}
        out['arms'][name]['ci95'] = boot(d, split, parts)
    pairs = [(f'{m}/skills', f'{m}/code') for m in ('sonnet55', 'opus55')]
    pairs += [('opus55/code', 'sonnet55/code'), ('opus55/skills', 'sonnet55/skills')]
    pairs += [(c, p) for c in conds for p in arms if p.startswith('pipe/')]
    for x, y in pairs:
        dd = {p: arms[x][p] - arms[y][p] for p in parts}
        out['pairs'][f'{x} - {y}'] = {'mean': st.mean(dd.values()), 'ci95': boot(dd, split, parts),
                                      'wins': sum(v > 1e-9 for v in dd.values()),
                                      'losses': sum(v < -1e-9 for v in dd.values())}
    out['per_part'] = {p: {k: round(arms[k][p], 4) for k in arms} for p in parts}

    print(f'{"arm":28s} {"benchA":>7} {"benchE":>7} {"all":>7}  95% CI')
    for k, r in out['arms'].items():
        print(f'{k:28s} {r["benchA"]:7.4f} {r["benchE"]:7.4f} {r["all"]:7.4f}  [{r["ci95"][0]:.4f}, {r["ci95"][1]:.4f}]')
    print()
    for c, d in detail.items():
        print(f'{c:16s} valid {d["delivered_valid"]}/{d["episodes"]}  verified-in-episode {d["verified_in_episode"]}  '
              f'valid-but-unverified {d["valid_but_unverified"]}  causes {d["causes"]}  stop {d["stop"]}  '
              f'mean {d["mean_s"]:.0f}s median {d["median_s"]:.0f}s  ${d["cost_per_episode"]:.3f}/ep  '
              f'repeats {[round(v, 4) for v in d["repeat_means"]]}')
    print()
    for k, v in out['pairs'].items():
        print(f'{k:36s} {v["mean"]:+.4f} [{v["ci95"][0]:+.4f}, {v["ci95"][1]:+.4f}]  W/L {v["wins"]}/{v["losses"]}')
    if a.out:
        json.dump(out, open(a.out, 'w'), indent=1)


if __name__ == '__main__':
    main()

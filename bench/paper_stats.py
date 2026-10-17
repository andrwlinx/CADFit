#!/usr/bin/env python3
"""
Every number the paper reports, recomputed from raw score files into results/.

  python3 bench/paper_stats.py      # -> results/fresh_arms.json, results/agent_skills.json, results/refine_study.json

Inputs: bench/runs/fresh_scores.json, fresh_section_control.json (60-part fresh cohort,
pipeline arms), bench/runs/agentsk_scores.json, agentsk_sens_scores.json (20-part
skills study), bench/runs/agentfr_study.log copies of the gated refine study summary.
CIs: paired percentile bootstrap over parts, 10,000 resamples, seed 0; the
family-wise versions use alpha = 0.05 / number of models (Bonferroni).
"""
import json
import math
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, 'bench', 'runs')
OUT = os.path.join(ROOT, 'results')


def mean(v):
    return sum(v) / len(v)


def paired(a, b, alpha=0.05, n=10000, seed=0):
    d = [x - y for x, y in zip(a, b)]
    r = random.Random(seed)
    bs = sorted(mean([d[r.randrange(len(d))] for _ in d]) for _ in range(n))
    w = sum(x > y + 1e-9 for x, y in zip(a, b))
    lo = sum(x < y - 1e-9 for x, y in zip(a, b))
    k = w + lo
    p = min(1.0, 2 * sum(math.comb(k, i) for i in range(max(w, lo), k + 1)) / 2 ** k) if k else 1.0
    return {'diff': mean(d), 'ci_lo': bs[int(alpha / 2 * n)], 'ci_hi': bs[int((1 - alpha / 2) * n) - 1],
            'alpha': alpha, 'wins': w, 'losses': lo, 'sign_p': p}


def split_of(part, index):
    return index.get(part, '?')


def fresh():
    S = json.load(open(os.path.join(RUNS, 'fresh_scores.json')))
    sc = json.load(open(os.path.join(RUNS, 'fresh_section_control.json')))
    idx = json.load(open(os.path.join(ROOT, 'bench', 'cadbench', 'index.json')))
    split = {r['file_id']: k for k, v in idx.items() for r in v}
    parts = sorted(S['fresh_base'])
    arms = {'A_base': 'fresh_base', 'B_rules': 'fresh_rules', 'C_beam': 'fresh_beamkh', 'D_beam_sections': 'fresh_beamsec'}
    g = lambda arm, k: [S[arm][p].get(k) or 0.0 for p in parts]  # noqa: E731
    res = {'n_parts': len(parts), 'arms': {}, 'paired': {}}
    for name, arm in arms.items():
        rec = [S[arm][p] for p in parts]
        res['arms'][name] = {
            'iou': mean(g(arm, 'iou')), 'iou_cad': mean(g(arm, 'iou_cad')),
            # CD is undefined without an output: averaged over measured outputs, with its denominator.
            'cd_measured': mean([r['cd'] for r in rec if r.get('cd') is not None]),
            'cd_n': sum(r.get('cd') is not None for r in rec),
            'cad_bad': sum(not (r.get('cad_built') and r.get('cad_valid')) for r in rec),
            'cad_unbuilt': sum(not r.get('cad_built') for r in rec),
            'mesh_cad_gap_parts': sum((r.get('iou') or 0) - (r.get('iou_cad') or 0) > 0.05 for r in rec),
            'by_split': {s: {'n': sum(split_of(p, split) == s for p in parts),
                             'iou': mean([S[arm][p]['iou'] for p in parts if split_of(p, split) == s]),
                             'iou_cad': mean([S[arm][p].get('iou_cad') or 0 for p in parts if split_of(p, split) == s])}
                         for s in ('benchA', 'benchE')}}
    bo = [sc[p]['best_of'] for p in parts]
    boc = [sc[p]['best_of_cad'] for p in parts]
    res['arms']['best_of_C_and_sections'] = {'iou': mean(bo), 'iou_cad': mean(boc)}
    res['arms']['sections_only'] = {'iou': mean([sc[p]['sections'] for p in parts])}
    steps = [('B_rules', 'A_base'), ('C_beam', 'B_rules'), ('D_beam_sections', 'C_beam'), ('D_beam_sections', 'A_base')]
    for k in ('iou', 'iou_cad'):
        for a, b in steps:
            res['paired'][f'{a}-{b}/{k}'] = paired(g(arms[a], k), g(arms[b], k))
    # Validity-gated IoU(CAD): 0 unless the program builds AND OCC accepts the shape and every solid.
    gated = lambda arm: [(S[arm][p].get('iou_cad') or 0.0) if (S[arm][p].get('cad_built') and S[arm][p].get('cad_valid'))
                         else 0.0 for p in parts]  # noqa: E731
    for name, arm in arms.items():
        rec = [S[arm][p] for p in parts]
        gap = [(r.get('iou') or 0) - (r.get('iou_cad') or 0) for r in rec]
        res['arms'][name]['iou_cad_valid_gated'] = mean(gated(arm))
        res['arms'][name]['gap'] = mean(gap)
        res['arms'][name]['gap_from_unbuilt'] = sum(x for x, r in zip(gap, rec) if not r.get('cad_built')) / len(rec)
        res['arms'][name]['gap_from_built'] = sum(x for x, r in zip(gap, rec) if r.get('cad_built')) / len(rec)
        res['arms'][name]['cad_built_invalid'] = sum(bool(r.get('cad_built')) and not r.get('cad_valid') for r in rec)
    for a, b in steps:
        res['paired'][f'{a}-{b}/iou_cad_valid_gated'] = paired(gated(arms[a]), gated(arms[b]))
        # Does the step's gain shrink when the program is executed? (CAD gain - mesh gain), paired over parts
        dc = [x - y for x, y in zip(g(arms[a], 'iou_cad'), g(arms[b], 'iou_cad'))]
        dm = [x - y for x, y in zip(g(arms[a], 'iou'), g(arms[b], 'iou'))]
        res['paired'][f'{a}-{b}/cad_gain_minus_mesh_gain'] = paired(dc, dm)
    for sp in ('benchA', 'benchE'):
        idx_sp = [i for i, p in enumerate(parts) if split_of(p, split) == sp]
        for k in ('iou', 'iou_cad'):
            res['paired'][f'D_beam_sections-A_base/{k}/{sp}'] = paired(
                [g('fresh_beamsec', k)[i] for i in idx_sp], [g('fresh_base', k)[i] for i in idx_sp])
    res['paired']['D_beam_sections-best_of/iou_cad'] = paired(g('fresh_beamsec', 'iou_cad'), boc)
    res['paired']['D_beam_sections-best_of/iou'] = paired(g('fresh_beamsec', 'iou'), bo)
    return res


MODELS = ['gemma4-31b', 'qwen36-35b-a3b', 'gptoss-120b', 'devstral2-24b', 'gptoss-20b', 'qwen38-27b']


def skills():
    S = json.load(open(os.path.join(RUNS, 'agentsk_scores.json')))
    P, C = S['parts'], S['conditions']
    col = lambda c: [C[c][p].get('iou_cad') or 0.0 for p in P]  # noqa: E731
    a = 0.05 / len(MODELS)
    res = {'n_parts': len(P), 'parts': P, 'bonferroni_alpha': a, 'conditions': {}, 'models': {}}
    for c in C:
        res['conditions'][c] = {'iou': mean([C[c][p].get('iou') or 0 for p in P]), 'iou_cad': mean(col(c))}
    for m in MODELS:
        s = col(f'{m}/skills')
        res['models'][m] = {
            'skills': mean(s), 'code': mean(col(f'{m}/code')),
            'skills_vs_code': paired(s, col(f'{m}/code')),
            'skills_vs_code_bonf': paired(s, col(f'{m}/code'), a),
            'skills_vs_policy': paired(s, col('no-llm-policy/skills')),
            'skills_vs_policy_bonf': paired(s, col('no-llm-policy/skills'), a),
            'skills_vs_beamsec': paired(s, col('pipeline/beamsec')),
            'skills_vs_beamsec_bonf': paired(s, col('pipeline/beamsec'), a),
            'skills_stops': dict(__import__('collections').Counter(C[f'{m}/skills'][p].get('stop') for p in P)),
            'code_stops': dict(__import__('collections').Counter(C[f'{m}/code'][p].get('stop') for p in P))}
    sens = os.path.join(RUNS, 'agentsk_sens_scores.json')
    if os.path.exists(sens):
        T = json.load(open(sens))['conditions']
        res['qwen38_32k_posthoc'] = {t: {'iou_cad_16k': mean(col(f'qwen38-27b/{t}')),
                                         'iou_cad_32k': mean([T[f'qwen38-27b/{t}'][p].get('iou_cad') or 0 for p in P])}
                                     for t in ('skills', 'code')}
    for c in C:  # validity-gated IoU(CAD) where validity is recorded
        if all('cad_valid' in C[c][p] for p in P):
            res['conditions'][c]['iou_cad_valid_gated'] = mean(
                [(C[c][p].get('iou_cad') or 0) if C[c][p].get('cad_valid') and C[c][p].get('cad_built') else 0 for p in P])
    pol = [C['no-llm-policy/skills'][p].get('trial_evaluations') or 0 for p in P]
    res['policy_trial_evaluations_mean'] = mean(pol)
    return res


def refine():
    """Gated refine study summary lines (agentfr1/2 logs: mesh IoU, 19 parts, judge IoU < 0.90 gate)."""
    out = {}
    for f in ('agentfr1.log', 'agentfr2.log'):
        p = os.path.join(RUNS, 'agentfr', f)
        if not os.path.exists(p):
            continue
        for line in open(p):
            if ' n=' in line and 'IoU' in line:
                name = line.split()[0]
                t = line.split()
                out.setdefault(name, {})[f] = {'n': int(t[1][2:]), 'iou': float(t[3]),
                                               'wl': t[t.index('W/L') + 1] if 'W/L' in t else None}
    return out


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for name, fn in (('fresh_arms', fresh), ('agent_skills', skills), ('refine_study', refine)):
        r = fn()
        json.dump(r, open(os.path.join(OUT, name + '.json'), 'w'), indent=1)
        print(name, 'written')

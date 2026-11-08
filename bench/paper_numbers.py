#!/usr/bin/env python3
"""
Write paper/numbers.tex: every result number the paper prints, as a LaTeX macro, generated
from the committed result files (PAPER_ACCEPTANCE_CONTRACT.md A2). A value whose source file
does not exist yet renders as \\pending{<what>} (visible in the PDF).

  .venv/bin/python bench/paper_numbers.py            # -> paper/numbers.tex
"""
import json
import os
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = os.path.join(ROOT, 'results')
OUT = os.path.join(ROOT, 'paper', 'numbers.tex')
macros = {}


def load(*path):
    p = os.path.join(R, *path)
    return json.load(open(p)) if os.path.exists(p) else None


def f(x, d=3, sign=False):
    s = f'{x:+.{d}f}' if sign else f'{x:.{d}f}'
    return s.replace('-', '\\textminus{}') if s.startswith('-') else s


def ci(lo, hi, d=3):
    return f'[{f(lo, d, True)}, {f(hi, d, True)}]'


def put(name, value):
    assert name.isalpha(), name
    macros[name] = value


def pending(name, what):
    put(name, f'\\pending{{{what}}}')


def pval(p):
    return '<10^{-4}' if p < 1e-4 else f'{p:.3f}' if p >= 0.001 else f'{p:.4f}'


def heldout():
    prim = load('heldout', 'h2_primary_local.json')
    sec = load('heldout', 'h2_secondary_local_no_section.json')
    pre = load('heldout', 'h2_primary_pre_recovery_local.json')
    tim = load('heldout', 'h2_timing_summary.json')
    for name, d in (('Prim', prim), ('Sec', sec), ('Pre', pre)):
        if d is None:
            pending(f'h{name}', f'{name} stats')
    arms = {}
    for d in (prim, sec):
        arms.update(d.get('runs', {}) if d else {})
    words = {'h2s0_d0': 'DZero', 'h2s0_dx': 'DX', 'v2x3': 'VTwo', 'v3x3': 'VThree', 'trimx3': 'Trim'}
    for k, w in words.items():
        a = arms.get(k)
        if not a:
            pending(f'h{w}', k)
            continue
        put(f'h{w}', f(a['mean_gated']))
        put(f'h{w}A', f(a['benchA']))
        put(f'h{w}E', f(a['benchE']))
        put(f'h{w}Valid', f"{a['valid']}")
    pairs = {}
    for d in (prim, sec):
        pairs.update(d.get('pairs', {}) if d else {})
    names = {'h2s0_dx:h2s0_d0': 'DXvsDZero', 'v2x3:h2s0_dx': 'VTwovsDX', 'v3x3:v2x3': 'VThreevsVTwo',
             'trimx3:v3x3': 'TrimvsVThree'}
    for k, w in names.items():
        c = pairs.get(k)
        if not c:
            pending(f'h{w}', k)
            continue
        put(f'h{w}', f(c['diff'], 3, True))
        put(f'h{w}CI', ci(*c['ci95']))
        put(f'h{w}WL', f"{c['wins']}/{c['losses']}")
        put(f'h{w}P', f"${pval(c['sign_p_holm'])}$")
        put(f'h{w}BothValid', f(c['both_valid_diff'], 4, True))
    if pre:
        c = pre['pairs']['h2s0_dx:h2s0_d0']
        put('hPreDXvsDZero', f(c['diff'], 3, True))
        put('hPreDXValid', f"{pre['runs']['h2s0_dx']['valid']}")
    pending('hTrimvsSection', 'trim vs section-only (running)')
    pending('hSection', 'section-only control (running)')
    pending('hRejudge', 'independent rejudge (running)')
    pending('hSurface', 'surface agreement (running)')
    if tim:
        for k, w in (('h2s0_d0', 'DZero'), ('h2s0_dx', 'DX')):
            put(f'hMin{w}', f(tim[k]['mean_min'], 1))
            put(f'hMed{w}', f(tim[k]['median_min'], 1))
            put(f'hHours{w}', f(tim[k]['total_h'], 0))
        for k, w in (('v2', 'VTwo'), ('v3', 'VThree')):
            rs = [tim[f'h2s{s}_{k}'] for s in range(3)]
            put(f'hMin{w}', f(st.mean(r['mean_min'] for r in rs), 1))
            put(f'hMed{w}', f(st.mean(r['median_min'] for r in rs), 1))
            put(f'hHours{w}', f(st.mean(r['total_h'] for r in rs), 0))
            put(f'hMinForty{w}', f(st.mean(r['mean40_min'] for r in rs), 1))


def trim_decomposition():
    m = load('tools_v3', 'h2_scores.json')
    if not m:
        return pending('hTrimProper', 'trim decomposition')
    proper, repass = [], []
    for s in range(3):
        t = load('tools_v3', f'h2s{s}_v3_trim.json')
        v3 = m[f'h2s{s}_v3']
        parts = sorted(v3)
        base = st.mean(v3[p]['iou_cad_gated'] for p in parts)
        nt = st.mean((t[p].get('gated_no_trim') or 0.0) if p in t else 0.0 for p in parts)
        fin = st.mean((t[p].get('gated') or 0.0) if p in t else 0.0 for p in parts)
        proper.append(fin - nt)
        repass.append(nt - base)
    valids = [sum(bool((load('tools_v3', f'h2s{s}_v3_trim.json').get(p) or {}).get('gated')) for p in sorted(m['h2s0_v3']))
              for s in range(3)]
    put('hValidTrimLo', str(min(valids)))
    put('hValidTrimHi', str(max(valids)))
    put('hTrimProperLo', f(min(proper), 4, True))
    put('hTrimProperHi', f(max(proper), 4, True))
    put('hRepassLo', f(min(repass), 4, True))
    put('hRepassHi', f(max(repass), 4, True))


def closed():
    c = load('closed', 'closed_vs_pipeline.json')
    if not c:
        return pending('cOpusCode', 'closed-model results')
    words = {'opus55/code': 'OpusCode', 'opus55/skills': 'OpusSkills', 'sonnet55/code': 'SonnetCode',
             'sonnet55/skills': 'SonnetSkills', 'pipe/d0': 'PipeDZero', 'pipe/dx': 'PipeDX',
             'pipe/v2x3': 'PipeVTwo', 'pipe/v3x3': 'PipeVThree', 'pipe/trim(x3)': 'PipeTrim'}
    for k, w in words.items():
        a = c['arms'][k]
        put(f'c{w}', f(a['all']))
        put(f'c{w}A', f(a['benchA']))
        put(f'c{w}E', f(a['benchE']))
        put(f'c{w}CI', f"[{f(a['ci95'][0])}, {f(a['ci95'][1])}]")
    for k, w in (('opus55/code', 'OpusCode'), ('opus55/skills', 'OpusSkills'),
                 ('sonnet55/code', 'SonnetCode'), ('sonnet55/skills', 'SonnetSkills')):
        d = c['agent_detail'][k]
        put(f'c{w}Valid', f"{d['delivered_valid']}/{d['episodes']}")
        put(f'c{w}NoOut', f"{d['causes'].get('no output', 0)}")
        put(f'c{w}Min', f(d['mean_s'] / 60, 1))
        put(f'c{w}Med', f(d['median_s'] / 60, 1))
        put(f'c{w}Cost', f(d['cost_per_episode'], 2))
        put(f'c{w}Unverified', f"{d['valid_but_unverified']}")
    pairs = {'opus55/code - pipe/v3x3': 'OpusCodeVsVThree', 'opus55/code - pipe/trim(x3)': 'OpusCodeVsTrim',
             'opus55/code - sonnet55/code': 'OpusVsSonnetCode', 'opus55/skills - opus55/code': 'OpusSkillsVsCode',
             'sonnet55/skills - sonnet55/code': 'SonnetSkillsVsCode', 'sonnet55/code - pipe/v3x3': 'SonnetCodeVsVThree'}
    for k, w in pairs.items():
        p = c['pairs'][k]
        put(f'c{w}', f(p['mean'], 3, True))
        put(f'c{w}CI', ci(*p['ci95']))
        put(f'c{w}WL', f"{p['wins']}/{p['losses']}")
    det = c['agent_detail']
    put('cDeliveredValid', str(sum(d['delivered_valid'] for d in det.values())))
    put('cDelivered', str(sum(d['episodes'] - d['causes'].get('no output', 0) for d in det.values())))
    put('cCostRetained', f(sum(d['cost_total'] for d in det.values()), 2))
    ts = load('closed', 'agentsk_f2_tool_seconds.json')
    if ts:
        share = {}
        for m in ('opus55', 'sonnet55'):
            tot = sum(v['total_s'] for k, v in ts.items() if k.startswith(f'{m}/code/'))
            share[m] = ts[f'{m}/code/add_code']['total_s'] / tot
        put('cAddCodeShareLo', f(100 * min(share.values()), 0))
        put('cAddCodeShareHi', f(100 * max(share.values()), 0))
        put('cMaxCall', f(max(v['max_s'] for v in ts.values()), 0))


def tools():
    t = load('tools_v3', 'tools_v3.json')
    if not t:
        return pending('tOpusSkillsVThree', 'tools-v3 results')
    for m, mw in (('opus55', 'Opus'), ('sonnet55', 'Sonnet')):
        for ts, tw in (('code', 'Code'), ('skills', 'Skills')):
            for v, vw in (('v2', 'VTwo'), ('v3', 'VThree')):
                k = f'{m}/{ts}/{v}'
                a, d = t['cells'][k], t['detail'][k]
                w = f't{mw}{tw}{vw}'
                put(w, f(a['all']))
                put(w + 'CI', f"[{f(a['ci95'][0])}, {f(a['ci95'][1])}]")
                put(w + 'Valid', f"{d['delivered_valid']}/{d['episodes']}")
                put(w + 'NoOut', str(d['no_output']))
                put(w + 'Min', f(d['mean_s'] / 60, 1))
                put(w + 'Med', f(d['median_s'] / 60, 1))
                put(w + 'Cost', f(d['cost_total'], 2))
    names = {'opus55/skills/v3 - opus55/skills/v2': 'OpusSkillsVersion', 'opus55/skills/v3 - opus55/code/v3': 'OpusSkillsVsCode',
             'opus55/code/v3 - opus55/code/v2': 'OpusCodeVersion', 'sonnet55/skills/v3 - sonnet55/skills/v2': 'SonnetSkillsVersion',
             'sonnet55/skills/v3 - sonnet55/code/v3': 'SonnetSkillsVsCode', 'sonnet55/code/v3 - sonnet55/code/v2': 'SonnetCodeVersion'}
    for k, w in names.items():
        c = t['comparisons'][k]
        put(f't{w}', f(c['mean'], 3, True))
        put(f't{w}CI', ci(*c['ci95']))
        put(f't{w}WL', f"{c['wins']}/{c['losses']}")
        put(f't{w}P', f"{c['sign_p']:.3f}")
        if 'holm_p' in c:
            put(f't{w}Holm', f"{c['holm_p']:.3f}")
    put('tCostTotal', f(sum(d['cost_total'] for d in t['detail'].values()), 2))


def classify(r):
    """valid / built-invalid / build error / missing / resource (timeout or rc -9) / setup (sandbox)."""
    if r is None:
        return 'missing'
    if r.get('cad_valid'):
        return 'valid'
    e = str(r.get('cad_error') or '')
    if 'ns_sandbox' in e:
        return 'setup'
    if e.startswith('timeout') or '(rc -9,' in e:
        return 'resource'
    if e == 'no program' or r.get('status') == 'no_model':
        return 'missing'
    return 'builtinvalid' if r.get('cad_built') else 'builderror'


WORDS = {'valid': 'Valid', 'builtinvalid': 'BuiltInvalid', 'builderror': 'BuildError', 'missing': 'Missing',
         'resource': 'Resource', 'setup': 'Setup'}


def failures():
    man = [it['file_id'] for it in json.load(open(os.path.join(ROOT, 'bench', 'cadbench', 'fresh2', 'manifest.json')))]
    for tag, path in (('', ('tools_v3', 'h2_scores.json')), ('Pre', ('heldout', 'h2_scores_pre_recovery_merged.json'))):
        m = load(*path)
        if not m:
            continue
        for run, w in (('h2s0_d0', 'DZero'), ('h2s0_dx', 'DX'), ('h2s0_v2', 'VTwoS'), ('h2s1_v2', 'VTwoSs'),
                       ('h2s2_v2', 'VTwoSss'), ('h2s0_v3', 'VThreeS'), ('h2s1_v3', 'VThreeSs'), ('h2s2_v3', 'VThreeSss')):
            cnt = {k: 0 for k in WORDS}
            for p in man:
                cnt[classify(m[run].get(p))] += 1
            for k, kw in WORDS.items():
                put(f'f{tag}{w}{kw}', str(cnt[k]))
            put(f'g{tag}{w}', f(st.mean(m[run].get(p, {}).get('iou_cad_gated', 0.0) for p in man)))
        for k, w in (('v2', 'VTwo'), ('v3', 'VThree')):
            put(f'h{tag}Mean{w}x', f(st.mean(st.mean(m[f'h2s{s}_{k}'][p]['iou_cad_gated'] for s in range(3)) for p in man)))
            valids = [sum(bool(m[f'h2s{s}_{k}'][p].get('cad_valid')) for p in man) for s in range(3)]
            put(f'h{tag}Valid{w}Lo', str(min(valids)))
            put(f'h{tag}Valid{w}Hi', str(max(valids)))
    cl = load('heldout', 'h2_env_cleared.json') or load('tools_v3', 'h2_env_cleared.json')
    if cl:
        tot = {}
        for entry in cl:
            if not entry.get('dry_run'):
                for run, v in entry['runs'].items():
                    tot[run] = len(v['cleared'])
        put('hRecoveredTotal', str(sum(tot.values())))
    for name, d in (('', load('heldout', 'h2_primary_local.json')), ('', load('heldout', 'h2_secondary_local_no_section.json'))):
        for k, c in (d or {}).get('pairs', {}).items():
            w = {'h2s0_dx:h2s0_d0': 'DXvsDZero', 'v2x3:h2s0_dx': 'VTwovsDX', 'v3x3:v2x3': 'VThreevsVTwo',
                 'trimx3:v3x3': 'TrimvsVThree'}[k]
            put(f'h{w}Neutral', str(300 - c['wins'] - c['losses']))


def agent_failures():
    c = load('closed', 'closed_vs_pipeline.json')
    if c:
        put('cValidUnverified', str(sum(d['valid_but_unverified'] for d in c['agent_detail'].values())))
    t = load('tools_v3', 'tools_v3.json')
    if t:
        for k, d in t['detail'].items():
            m, ts, v = k.split('/')
            w = f"t{'Opus' if m == 'opus55' else 'Sonnet'}{'Code' if ts == 'code' else 'Skills'}{'VTwo' if v == 'v2' else 'VThree'}"
            put(w + 'Invalid', str(d['episodes'] - d['delivered_valid'] - d['no_output']))
    if t:
        unv = 0
        for v in ('v2', 'v3'):
            for r in ('r0', 'r1', 'r2'):
                for cond in load('tools_v3', f'tv_{v}_{r}_scores.json')['conditions'].values():
                    unv += sum(bool(x.get('cad_valid')) and not x.get('verified_in_episode') for x in cond.values())
        put('tValidUnverified', str(unv))
        put('tDeliveredValid', str(sum(d['delivered_valid'] for d in t['detail'].values())))
        put('tEpisodes', str(sum(d['episodes'] for d in t['detail'].values())))
    # Tools-v3 timing contrasts (descriptive): per-part mean minutes over the three repeats.
    import random
    sub = json.load(open(os.path.join(ROOT, 'bench', 'cadbench', 'fresh3_parts.json')))['parts']
    split = {p: k for k, v in sub.items() for p in v}
    parts = sorted(split)
    for m, mw in (('opus55', 'Opus'), ('sonnet55', 'Sonnet')):
        for ts, tw in (('code', 'Code'), ('skills', 'Skills')):
            mins = {}
            for v in ('v2', 'v3'):
                reps = [load('tools_v3', f'tv_{v}_{r}_scores.json')['conditions'][f'{m}/{ts}'] for r in ('r0', 'r1', 'r2')]
                mins[v] = {p: st.mean(x[p]['seconds'] for x in reps) / 60 for p in parts}
            d = {p: mins['v3'][p] - mins['v2'][p] for p in parts}
            rng = random.Random(0)
            groups = [[d[p] for p in parts if split[p] == s] for s in sorted(set(split.values()))]
            bs = sorted(sum(sum(rng.choices(g, k=len(g))) for g in groups) / len(parts) for _ in range(10000))
            faster = sum(v < 0 for v in d.values())
            slower = sum(v > 0 for v in d.values())
            from math import comb
            n, k = faster + slower, min(faster, slower)
            pv = min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)
            w = f'tTime{mw}{tw}'
            put(w, f(st.mean(d.values()), 1, True))
            put(w + 'CI', f'[{f(bs[250], 1, True)}, {f(bs[9750], 1, True)}]')
            put(w + 'Faster', str(faster))
            put(w + 'P', '$<10^{-4}$' if pv < 1e-4 else f'{pv:.2f}')


def costs():
    import glob as _g
    d = os.path.join(R, 'review_bundle_2026-11-05', 'agentsk_f2', 'opus55_node4002_failed')
    rs = [json.load(open(x)) for x in _g.glob(os.path.join(d, '*', '*', 'result.json'))]
    diag = json.load(open(os.path.join(d, 'diagnosis.json'))) if os.path.exists(os.path.join(d, 'diagnosis.json')) else {}
    put('cDiscardedRecords', str(len(rs)))
    put('cDiscardedDiagnosed', str(len(diag)))
    put('cDiscardedCost', f(sum(r.get('cost_usd') or 0 for r in rs), 2))
    put('cDiscardedTimeoutEpisodes', str(sum(v['exec_timeouts_90s'] > 0 for v in diag.values())))
    put('cDiscardedTimeouts', str(sum(v['exec_timeouts_90s'] for v in diag.values())))
    fail = os.path.join(R, 'tools_v3', 'episodes', 'tv_api_failed')
    rs = [json.load(open(x)) for x in _g.glob(os.path.join(fail, '*', '*', '*', '*', 'result.json'))]
    put('tApiFailed', str(len(rs)))
    put('tApiFailedCost', f(sum(r.get('cost_usd') or 0 for r in rs), 2))


def equivalence():
    e = load('tools', 'equivalence.json')
    if not e:
        return pending('eDedup', 'equivalence tests')
    put('eDedup', f"{e['dedup']['identical']}/{e['dedup']['cases']}")
    put('eRotation', f"{e['rotation']['bit_identical']}/{e['rotation']['cases']}")
    put('eJudge', f"{e['judge']['identical']}/{e['judge']['pairs']}")
    put('eFit', f"{e['fitting']['identical']}/{e['fitting']['sketches']}")
    put('eFitParts', str(e['fitting']['parts']))
    put('eFitOld', f(e['fitting']['seconds_old'], 0))
    put('eFitNew', f(e['fitting']['seconds_new'], 0))
    p = load('tools', 'profile_v2_local.json')
    if p:
        ex = [c for r in p['parts'].values() for c in r['calls'] if c['tool'] == 'extract_sketch']
        put('eExtractFitShare', f(100 * sum(c.get('fit', 0) for c in ex) / sum(c['seconds'] for c in ex), 1))
        put('eProfileParts', str(len(p['parts'])))


def main():
    equivalence()
    heldout()
    failures()
    agent_failures()
    costs()
    trim_decomposition()
    closed()
    tools()
    lines = ['% Generated by bench/paper_numbers.py from results/ -- do not edit by hand.',
             '\\providecommand{\\pending}[1]{\\textcolor{red}{[pending: #1]}}']
    lines += [f'\\newcommand{{\\{k}}}{{{v}}}' for k, v in sorted(macros.items())]
    open(OUT, 'w').write('\n'.join(lines) + '\n')
    print(f'{len(macros)} macros -> {OUT}; pending: {sum("pending" in v for v in macros.values())}')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
results/*.json -> paper/numbers.tex: one LaTeX macro per reported number, so no result
number is typed by hand in paper/sections/*.tex.

  python3 bench/paper_stats.py && python3 bench/paper_numbers.py

Rounding: 3 decimals; an interval endpoint whose 3-decimal rounding would read 0.000 or
flip sign is printed with 4 significant digits instead (contract assertion 2).
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, 'results')
ARMS = {'A_base': 'Base', 'B_rules': 'Rules', 'C_beam': 'Beam', 'D_beam_sections': 'Sec'}
MODELS = {'gemma4-31b': 'Gemma', 'qwen36-35b-a3b': 'QwenSix', 'gptoss-120b': 'GptBig',
          'devstral2-24b': 'Devstral', 'gptoss-20b': 'GptSmall', 'qwen38-27b': 'QwenEight'}
L = []


def num(x, signed=False):
    s = f'{x:+.3f}' if signed else f'{x:.3f}'
    if x != 0 and (float(s) == 0 or (float(s) > 0) != (x > 0)):
        s = f'{x:+.4g}' if signed else f'{x:.4g}'
    return s.replace('-', '\\ensuremath{-}')  # a typeset minus, not a hyphen


def put(name, value):
    assert name.isalpha(), name
    L.append(f'\\newcommand{{\\{name}}}{{{value}}}')


def put_paired(prefix, p):
    put(prefix + 'Diff', num(p['diff'], True))
    put(prefix + 'Lo', num(p['ci_lo'], True))
    put(prefix + 'Hi', num(p['ci_hi'], True))
    put(prefix + 'CI', f"[{num(p['ci_lo'], True)}, {num(p['ci_hi'], True)}]")
    put(prefix + 'Wins', str(p['wins']))
    put(prefix + 'Losses', str(p['losses']))


def fresh():
    F = json.load(open(os.path.join(RES, 'fresh_arms.json')))
    put('nFresh', str(F['n_parts']))
    for k, n in ARMS.items():
        a = F['arms'][k]
        put(f'arm{n}Iou', num(a['iou']))
        put(f'arm{n}Cad', num(a['iou_cad']))
        put(f'arm{n}Gated', num(a['iou_cad_valid_gated']))
        put(f'arm{n}Cd', f"{a['cd_measured']:.4f}")
        put(f'arm{n}CdN', str(a['cd_n']))
        put(f'arm{n}Gap', num(a['gap']))
        put(f'arm{n}GapUnbuilt', num(a['gap_from_unbuilt']))
        put(f'arm{n}GapBuilt', num(a['gap_from_built']))
        put(f'arm{n}Unbuilt', str(a['cad_unbuilt']))
        put(f'arm{n}BuiltInvalid', str(a['cad_built_invalid']))
        put(f'arm{n}Bad', str(a['cad_bad']))
        for sp, s in (('benchA', 'SplitA'), ('benchE', 'SplitE')):
            put(f'arm{n}{s}Iou', num(a['by_split'][sp]['iou']))
            put(f'arm{n}{s}Cad', num(a['by_split'][sp]['iou_cad']))
    for sp, s in (('benchA', 'SplitA'), ('benchE', 'SplitE')):
        put(f'n{s}', str(F['arms']['A_base']['by_split'][sp]['n']))
    put('bestOfIou', num(F['arms']['best_of_C_and_sections']['iou']))
    put('bestOfCad', num(F['arms']['best_of_C_and_sections']['iou_cad']))
    put('sectionsOnlyIou', num(F['arms']['sections_only']['iou']))
    P = F['paired']
    steps = {'B_rules-A_base': 'RulesBase', 'C_beam-B_rules': 'BeamRules',
             'D_beam_sections-C_beam': 'SecBeam', 'D_beam_sections-A_base': 'SecBase'}
    mets = {'iou': 'Iou', 'iou_cad': 'Cad', 'iou_cad_valid_gated': 'Gated', 'cad_gain_minus_mesh_gain': 'Shrink'}
    for s, sn in steps.items():
        for m, mn in mets.items():
            put_paired(f'd{sn}{mn}', P[f'{s}/{m}'])
    for sp, s in (('benchA', 'SplitA'), ('benchE', 'SplitE')):
        for m, mn in (('iou', 'Iou'), ('iou_cad', 'Cad')):
            put_paired(f'dSecBase{s}{mn}', P[f'D_beam_sections-A_base/{m}/{sp}'])
    put_paired('dSecBestOfCad', P['D_beam_sections-best_of/iou_cad'])
    put_paired('dSecBestOfIou', P['D_beam_sections-best_of/iou'])


def agents():
    A = json.load(open(os.path.join(RES, 'agent_skills.json')))
    put('nAgentParts', str(A['n_parts']))
    put('bonfLevel', f"{100 * (1 - A['bonferroni_alpha']):.2f}")
    C = A['conditions']
    put('agentPipeSec', num(C['pipeline/beamsec']['iou_cad']))
    put('agentPipeSecGated', num(C['pipeline/beamsec']['iou_cad_valid_gated']))
    put('agentPipeBeam', num(C['pipeline/beamkh']['iou_cad']))
    put('agentPipeBeamGated', num(C['pipeline/beamkh']['iou_cad_valid_gated']))
    put('agentPipeBestOf', num(C['pipeline/best_of_beam_section']['iou_cad']))
    put('policyCad', num(C['no-llm-policy/skills']['iou_cad']))
    put('policyGated', num(C['no-llm-policy/skills']['iou_cad_valid_gated']))
    put('policyTrials', f"{A['policy_trial_evaluations_mean']:.0f}")
    gains = []
    for m, n in MODELS.items():
        r = A['models'][m]
        put(f'm{n}Skills', num(r['skills']))
        put(f'm{n}Code', num(r['code']))
        put(f'm{n}SkillsGated', num(C[f'{m}/skills']['iou_cad_valid_gated']))
        put(f'm{n}CodeGated', num(C[f'{m}/code']['iou_cad_valid_gated']))
        put_paired(f'm{n}VsCode', r['skills_vs_code_bonf'])
        put_paired(f'm{n}VsPolicy', r['skills_vs_policy_bonf'])
        put_paired(f'm{n}VsPolicyNominal', r['skills_vs_policy'])
        put_paired(f'm{n}VsPipe', r['skills_vs_beamsec_bonf'])
        gains.append(r['skills_vs_code_bonf']['diff'])
    idx = json.load(open(os.path.join(ROOT, 'bench', 'cadbench', 'index.json')))
    split = {r['file_id']: k for k, v in idx.items() for r in v}
    put('nSampleA', str(sum(split.get(p) == 'benchA' for p in A['parts'])))
    put('nSampleE', str(sum(split.get(p) == 'benchE' for p in A['parts'])))
    drops = [C[f'{m}/skills']['iou_cad'] - C[f'{m}/skills']['iou_cad_valid_gated'] for m in MODELS]
    put('skillsGatedMaxDrop', num(max(drops)))
    put('skillsGainMin', num(min(gains)))
    put('skillsGainMax', num(max(gains)))
    q = A['models']['qwen38-27b']
    put('qwenCodeNoTool', str(q['code_stops'].get('no tool call', 0)))
    put('qwenSkillsNoTool', str(q['skills_stops'].get('no tool call', 0)))
    s = A.get('qwen38_32k_posthoc')
    if s:
        for t, tn in (('skills', 'Skills'), ('code', 'Code')):
            put(f'qwenPosthoc{tn}', num(s[t]['iou_cad_32k']))


def extra():
    p = os.path.join(RES, 'agent_extra.json')
    if not os.path.exists(p):  # jobs still running: every macro extra() defines, as a visible placeholder
        names = ['gemmaRunOne', 'gemmaRunTwo', 'gemmaRunThree', 'gemmaRunMean', 'gemmaRunMin', 'gemmaRunMax',
                 'gemmaCodesec', 'gemmaCodesecGated', 'policyMatchedCad', 'policyMatchedGated',
                 'policyMatchedTrials', 'policyMatchedCalls']
        for pre in ['gemmaCodesecVsCode', 'gemmaSkillsVsCodesec'] + [f'm{n}VsMatched' for n in MODELS.values()]:
            names += [pre + x for x in ('Diff', 'Lo', 'Hi', 'CI', 'Wins', 'Losses')]
        for k in names:
            put(k, '\\textbf{PENDING}')
        return
    E = json.load(open(p))
    runs = E['gemma_skills_runs']
    for k, v in zip(('One', 'Two', 'Three'), runs):
        put(f'gemmaRun{k}', num(v))
    put('gemmaRunMean', num(sum(runs) / len(runs)))
    put('gemmaRunMin', num(min(runs)))
    put('gemmaRunMax', num(max(runs)))
    put('gemmaCodesec', num(E['gemma_codesec']))
    put('gemmaCodesecGated', num(E['gemma_codesec_gated']))
    put_paired('gemmaCodesecVsCode', E['codesec_vs_code'])
    put_paired('gemmaSkillsVsCodesec', E['skills_vs_codesec'])
    put('policyMatchedCad', num(E['policy_matched']))
    put('policyMatchedGated', num(E['policy_matched_gated']))
    put('policyMatchedTrials', f"{E['policy_matched_trials_mean']:.1f}")
    put('policyMatchedCalls', f"{E['policy_matched_calls_mean']:.1f}")
    for m, n in MODELS.items():
        put_paired(f'm{n}VsMatched', E['vs_matched_bonf'][m])


def misc():
    R = json.load(open(os.path.join(RES, 'refine_study.json')))
    pipe = R['pipeline']['agentfr1.log']
    put('refN', str(pipe['n']))
    put('refPipe', num(pipe['iou']))
    ag = R['RedHatAI__Qwen3.8-27B-INT4/refine']
    put('refAgentOne', num(ag['agentfr1.log']['iou']))
    put('refAgentTwo', num(ag['agentfr2.log']['iou']))
    put('refAgentOneWL', ag['agentfr1.log']['wl'].replace('/', '--'))
    put('refAgentTwoWL', ag['agentfr2.log']['wl'].replace('/', '--'))
    put('refNoop', num(R['noop/refine']['agentfr1.log']['iou']))
    put('refSearch', num(R['search/refine']['agentfr1.log']['iou']))
    put('refSearchWL', R['search/refine']['agentfr1.log']['wl'].replace('/', '--'))
    Q = json.load(open(os.path.join(RES, 'qwen38_traces.json')))
    put('qwenTraceN', str(Q['code']['episodes_no_tool_call']))
    put('qwenTraceMinK', f"{Q['code']['final_reasoning_chars_min'] / 1000:.1f}")
    put('qwenTraceMaxK', f"{Q['code']['final_reasoning_chars_max'] / 1000:.1f}")
    T = json.load(open(os.path.join(RES, 'tool_usage.json')))
    for tool, tn in (('extract_sketch', 'Extract'), ('fit_extrude', 'Extrude'), ('fit_revolve', 'Revolve'),
                     ('section_extrude', 'SecExt'), ('section', 'Section')):
        v = [T[m]['per_episode'].get(tool, 0.0) for m in MODELS]
        put(f'use{tn}Min', f'{min(v):.1f}')
        put(f'use{tn}Max', f'{max(v):.1f}')
    F = json.load(open(os.path.join(ROOT, 'bench', 'runs', 'fresh_scores.json')))['fresh_beamkh']
    built = [(v['iou'] - (v.get('iou_cad') or 0)) for v in F.values() if v.get('cad_built')]
    put('beamMaxBuiltGap', num(max(built)))


if __name__ == '__main__':
    fresh()
    agents()
    extra()
    misc()
    out = os.path.join(ROOT, 'paper', 'numbers.tex')
    open(out, 'w').write('% generated by bench/paper_numbers.py from results/*.json -- do not edit\n'
                         + '\n'.join(L) + '\n')
    print(f'{len(L)} macros -> {out}')

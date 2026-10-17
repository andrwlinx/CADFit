#!/usr/bin/env python3
"""Data figures for the paper, from results/*.json and bench/runs/fresh_scores.json.

  python3 paper/figures/make_figures.py   # -> paper/figures/{hero,mesh_vs_cad}.pdf
"""
import json
import os
import random

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
R = lambda f: json.load(open(os.path.join(ROOT, f)))  # noqa: E731
plt.rcParams.update({'font.size': 8, 'font.family': 'serif', 'axes.spines.top': False,
                     'axes.spines.right': False, 'pdf.fonttype': 42})
MESH, CAD = '#9bb7d4', '#1f4e79'


def boot_ci(v, n=10000, seed=0):
    r = random.Random(seed)
    m = sorted(sum(v[r.randrange(len(v))] for _ in v) / len(v) for _ in range(n))
    return m[250], m[9749]


def main():
    S = R('bench/runs/fresh_scores.json')
    parts = sorted(S['fresh_base'])
    arms = [('A\nbase', 'fresh_base'), ('B\n+rules', 'fresh_rules'), ('C\n+beam', 'fresh_beamkh'),
            ('D\n+sect.', 'fresh_beamsec')]
    sk = R('results/agent_skills.json')
    names = {'gemma4-31b': 'Gemma-4-31B', 'qwen36-35b-a3b': 'Qwen3.6-35B-A3B', 'gptoss-120b': 'gpt-oss-120b',
             'devstral2-24b': 'Devstral-S-2-24B', 'gptoss-20b': 'gpt-oss-20b', 'qwen38-27b': 'Qwen3.8-27B'}
    order = sorted(names, key=lambda m: sk['models'][m]['skills'])

    SC = R('bench/runs/fresh_section_control.json')
    cols = {lab: {'iou': [S[arm][p].get('iou') or 0.0 for p in parts],
                  'iou_cad': [S[arm][p].get('iou_cad') or 0.0 for p in parts],
                  'bad': (sum(not S[arm][p].get('cad_built') for p in parts),
                          sum(bool(S[arm][p].get('cad_built')) and not S[arm][p].get('cad_valid') for p in parts))}
            for lab, arm in arms}
    cols['best-of\n(C, sect.)'] = {'iou': [SC[p]['best_of'] for p in parts],
                                     'iou_cad': [SC[p]['best_of_cad'] for p in parts], 'bad': None}
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.0, 2.7), gridspec_kw={'width_ratios': [1.15, 1]})
    w = 0.38
    for i, (lab, col) in enumerate(cols.items()):
        for j, (k, c, nm) in enumerate((('iou', MESH, 'mesh IoU (reported mesh)'),
                                        ('iou_cad', CAD, 'IoU(CAD) (executed program)'))):
            v = col[k]
            m = sum(v) / len(v)
            lo, hi = boot_ci(v)
            a.bar(i + (j - 0.5) * w, m, w, color=c, yerr=[[m - lo], [hi - m]], capsize=2, ecolor='0.3',
                  label=nm if i == 0 else None, linewidth=0)
            a.text(i + (j - 0.5) * w, 0.705, f'{m:.3f}', ha='center', va='bottom', fontsize=6, rotation=90,
                   color='white' if j else 'black')
            if j == 1:
                bad = col['bad']
                a.text(i + 0.5 * w, hi + 0.004, f'{bad[0]}+{bad[1]}' if bad else 'n/m', ha='center', va='bottom',
                       fontsize=5.5, color='#b03a2e')
    a.set_xticks(range(len(cols)), list(cols), fontsize=6.5)
    a.set_xlim(-0.6, len(cols) - 0.4)
    a.set_ylim(0.7, 1.08)
    a.set_yticks([0.7, 0.8, 0.9, 1.0])
    a.set_ylabel('mean over 60 fresh parts')
    a.set_title('(a) Search arms, 60 parts: mesh vs executed CAD', fontsize=8)
    a.legend(frameon=False, fontsize=5.5, loc='upper left', ncol=2,
             title='red: unbuilt + OCC-invalid programs (of 60)', title_fontsize=5.5)

    for i, m in enumerate(order):
        s, c = sk['models'][m]['skills'], sk['models'][m]['code']
        b.plot([c, s], [i, i], color='0.75', lw=2, zorder=1)
        b.scatter([c], [i], color='white', edgecolor=CAD, s=22, zorder=2, label='code only' if i == 0 else None)
        b.scatter([s], [i], color=CAD, s=22, zorder=3, label='+ CADFit skills' if i == 0 else None)
    ex_path = os.path.join(ROOT, 'results', 'agent_extra.json')
    if os.path.exists(ex_path):
        ex = json.load(open(ex_path))
        g = order.index('gemma4-31b')
        runs = ex['gemma_skills_runs']
        b.plot([min(runs), max(runs)], [g + 0.22, g + 0.22], color=CAD, lw=1)
        b.text(max(runs) + 0.01, g + 0.22, '3-run range', fontsize=5.5, va='center', color=CAD)
        b.scatter([ex['gemma_codesec']], [g - 0.22], marker='^', color='#d68910', s=20, zorder=3,
                  label='Gemma: code + section_extrude')
        pm = ex['policy_matched']
        b.axvline(pm, color='0.55', ls='-.', lw=1)
        b.text(pm - 0.008, len(order) - 0.5, f'budget-matched\npolicy {pm:.3f}', color='0.4', fontsize=5.5,
               ha='right', va='top')
    pd = sk['conditions']['pipeline/beamsec']['iou_cad']
    pol = sk['conditions']['no-llm-policy/skills']['iou_cad']
    b.axvline(pd, color='#b03a2e', ls='--', lw=1)
    b.axvline(pol, color='0.4', ls=':', lw=1)
    b.text(pd + 0.008, -1.05, f'pipeline D\n{pd:.3f}', color='#b03a2e', fontsize=5.5, ha='left', va='bottom')
    b.text(pol - 0.008, -1.05, f'policy (+{sk["policy_trial_evaluations_mean"]:.0f} free\nGT trials/part) {pol:.3f}',
           color='0.3', fontsize=5.5, ha='right', va='bottom')
    b.set_yticks(range(len(order)), [names[m] for m in order])
    b.set_xlim(0.0, 1.0)
    b.set_ylim(-1.15, len(order) - 0.4)
    b.set_xlabel('mean IoU(CAD); failed episodes score 0')
    b.set_title('(b) Open-weight agents, 20 parts: code vs skills', fontsize=8)
    b.legend(frameon=False, fontsize=5.5, loc='upper left')
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, 'hero.pdf'))

    fig, axs = plt.subplots(1, 2, figsize=(5.0, 2.4), sharey=True)
    for ax, (lab, arm) in zip(axs, arms[2:]):
        x = [S[arm][p]['iou'] for p in parts]
        y = [S[arm][p].get('iou_cad') or 0.0 for p in parts]
        bad = [not (S[arm][p].get('cad_built') and S[arm][p].get('cad_valid')) for p in parts]
        ax.plot([0, 1], [0, 1], color='0.7', lw=0.8)
        ax.scatter([u for u, q in zip(x, bad) if not q], [v for v, q in zip(y, bad) if not q], s=9, color=CAD,
                   label='valid program')
        ax.scatter([u for u, q in zip(x, bad) if q], [v for v, q in zip(y, bad) if q], s=14, marker='x',
                   color='#b03a2e', label='unbuilt / OCC-invalid')
        ax.set_title(lab.replace('\n', ' '), fontsize=8)
        ax.set_xlabel('mesh IoU')
        ax.set_xlim(0.4, 1.01)
        ax.set_title(lab.replace('\n', ' ') + ' (failures at 0)', fontsize=8)
        ax.set_ylim(-0.03, 1.01)
    axs[0].set_ylabel('IoU(CAD)')
    axs[0].legend(frameon=False, fontsize=6, loc='upper left')
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, 'mesh_vs_cad.pdf'))
    print('ok')


if __name__ == '__main__':
    main()

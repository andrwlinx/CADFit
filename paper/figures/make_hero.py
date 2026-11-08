"""Figure 1 (paper/figures/hero.pdf).

(a) Held-out pipeline arms on 300 fresh2 parts: validity-gated IoU of the executed program,
    95% split-stratified bootstrap interval over parts (repeats averaged within part for
    v2/v3/trim), and the number of parts without a valid delivery (in at least one seed for the
    three-seed arms: printed as the mean count). Source: results/tools_v3/h2_scores.json (after
    the recovery amendment), results/tools_v3/h2s*_v3_trim.json.
(b) The 40 reserved fresh2 parts: Claude agents (3 episodes, delivered programs re-judged) and the
    pipeline arms on the same parts. Source: results/closed/closed_vs_pipeline.json.

  .venv/bin/python paper/figures/make_hero.py
"""
import json
import os
import random
import statistics as st

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
plt.rcParams.update({'font.family': 'serif', 'font.size': 9, 'pdf.fonttype': 42})
PIPE, AGENT_CODE, AGENT_SKILLS, INK, MUTED = '#2a78d6', '#eb6834', '#1baf7a', '#0b0b0b', '#52514e'


def boot(vals, split, parts, n=5000, seed=0):
    rng = random.Random(seed)
    groups = [[vals[p] for p in parts if split[p] == s] for s in sorted(set(split.values()))]
    m = sorted(sum(sum(rng.choices(g, k=len(g))) for g in groups) / len(parts) for _ in range(n))
    return m[int(0.025 * n)], m[int(0.975 * n)]


def panel_a(ax):
    m = json.load(open(os.path.join(ROOT, 'results', 'tools_v3', 'h2_scores.json')))
    man = json.load(open(os.path.join(ROOT, 'bench', 'cadbench', 'fresh2', 'manifest.json')))
    split = {it['file_id']: it['split'] for it in man}
    parts = sorted(split)
    trims = [json.load(open(os.path.join(ROOT, 'results', 'tools_v3', f'h2s{s}_v3_trim.json'))) for s in range(3)]

    def gated(run, p):
        return m[run].get(p, {}).get('iou_cad_gated', 0.0)

    arms = [('d0', ['h2s0_d0'], None), ('dx', ['h2s0_dx'], None),
            ('v2', ['h2s0_v2', 'h2s1_v2', 'h2s2_v2'], None),
            ('v3', ['h2s0_v3', 'h2s1_v3', 'h2s2_v3'], None),
            ('trim', None, trims)]
    ticks = []
    for i, (lab, runs, tr) in enumerate(arms):
        if tr is None:
            vals = {p: st.mean(gated(r, p) for r in runs) for p in parts}
            bad = st.mean(sum(gated(r, p) == 0 for p in parts) for r in runs)
        else:
            vals = {p: st.mean((t[p].get('gated') or 0.0) if p in t else 0.0 for t in tr) for p in parts}
            bad = st.mean(sum(((t[p].get('gated') or 0.0) if p in t else 0.0) == 0 for p in parts) for t in tr)
        mu = st.mean(vals.values())
        lo, hi = boot(vals, split, parts)
        ax.errorbar(i, mu, yerr=[[mu - lo], [hi - mu]], fmt='o', color=PIPE, ecolor=INK, capsize=2.5, lw=0.8, ms=5)
        nb = f'{bad:.0f}' if abs(bad - round(bad)) < 0.05 else f'{bad:.1f}'
        ax.text(i, hi + 0.004, f'{mu:.3f}', ha='center', va='bottom', fontsize=7)
        ticks.append(f'{lab}\n({nb})')
    ax.set_xticks(range(len(arms)), ticks, fontsize=7)
    ax.set_xlim(-0.5, len(arms) - 0.5)
    ax.set_ylim(0.70, 1.02)
    ax.set_ylabel('gated IoU of executed program')
    ax.set_title('(a) Optimizer, 300 held-out parts', fontsize=9)
    ax.set_xlabel('arm (parts without a valid replay)', fontsize=7.5)


def panel_b(ax):
    c = json.load(open(os.path.join(ROOT, 'results', 'closed', 'closed_vs_pipeline.json')))
    rows = [('pipe/d0', 'optimizer d0', PIPE, 'D'), ('pipe/v3x3', 'optimizer v3', PIPE, 'D'),
            ('pipe/trim(x3)', 'optimizer + trim', PIPE, 'D'),
            ('sonnet55/skills', 'Sonnet + CADFit tools', AGENT_SKILLS, 's'), ('sonnet55/code', 'Sonnet + code', AGENT_CODE, 'o'),
            ('opus55/skills', 'Opus + CADFit tools', AGENT_SKILLS, 's'), ('opus55/code', 'Opus + code', AGENT_CODE, 'o')]
    for i, (k, lab, col, mk) in enumerate(rows):
        a = c['arms'][k]
        ax.errorbar(a['all'], i, xerr=[[a['all'] - a['ci95'][0]], [a['ci95'][1] - a['all']]], fmt=mk, color=col,
                    ecolor=INK, capsize=2.5, lw=0.8, ms=5)
        ax.text(a['ci95'][1] + 0.004, i, f"{a['all']:.3f}", va='center', fontsize=8)
    ax.set_yticks(range(len(rows)), [r[1] for r in rows], fontsize=7.5)
    ax.set_ylim(-0.5, len(rows) - 0.5)
    ax.set_xlim(0.70, 1.02)
    ax.set_xlabel('gated IoU of delivered program')
    ax.set_title('(b) Agents vs optimizer, 40 parts', fontsize=9)
    ax.set_xlim(0.70, 1.04)


def main():
    fig, axs = plt.subplots(1, 2, figsize=(7.0, 2.6), gridspec_kw={'width_ratios': [1.15, 1]})
    panel_a(axs[0])
    panel_b(axs[1])
    for ax in axs:
        for s in ('top', 'right'):
            ax.spines[s].set_visible(False)
        ax.tick_params(colors=MUTED)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, 'hero.pdf'))
    fig.savefig(os.path.join(HERE, 'hero.png'), dpi=200)


if __name__ == '__main__':
    main()

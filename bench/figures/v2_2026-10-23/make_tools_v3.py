"""Tools v2 vs v3 (review-stage/TOOLS_V3_PROTOCOL.md): Claude Opus/Sonnet 5.5 with plain
code and with CADFit tools on the 40 fresh3 parts, three episodes per part.

  .venv/bin/python bench/figures/v2_2026-10-23/make_tools_v3.py

simple_tools_v3.png   score (delivered program, common CAD judge, 95% CI) and minutes per part,
                      old tools (v2) vs new tools (v3), for each model x toolset

Input: results/tools_v3/tools_v3.json (bench/analysis/tools_v3.py).
"""
import json
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
plt.rcParams.update({'font.family': 'sans-serif', 'font.size': 12})
OLD, NEW = '#6250d6', '#1baf7a'   # validated categorical pair (dataviz palette slots 7, 3); values labelled
INK, MUTED = '#0b0b0b', '#52514e'
GROUPS = [('opus55', 'code', 'Opus\nplain code'), ('opus55', 'skills', 'Opus\nCadFit tools'),
          ('sonnet55', 'code', 'Sonnet\nplain code'), ('sonnet55', 'skills', 'Sonnet\nCadFit tools')]


def style(ax, title):
    ax.set_title(title, fontsize=13)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED)
    ax.set_xticks(range(len(GROUPS)), [g[2] for g in GROUPS], fontsize=10.5)


def main():
    r = json.load(open(os.path.join(ROOT, 'results', 'tools_v3', 'tools_v3.json')))
    cells, det = r['cells'], r['detail']
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.6))
    w = 0.36
    for j, (v, c, lab) in enumerate((('v2', OLD, 'old tools (v2)'), ('v3', NEW, 'new tools (v3)'))):
        for i, (m, t, _) in enumerate(GROUPS):
            x = i + (j - 0.5) * (w + 0.03)
            a, d = cells[f'{m}/{t}/{v}'], det[f'{m}/{t}/{v}']
            axs[0].bar(x, a['all'], w, color=c, label=lab if i == 0 else None)
            axs[0].errorbar(x, a['all'], yerr=[[a['all'] - a['ci95'][0]], [a['ci95'][1] - a['all']]],
                            color=INK, capsize=3, lw=1)
            axs[0].text(x, a['ci95'][1] + 0.002, f'{a["all"]:.3f}', ha='center', va='bottom', fontsize=9.5)
            mins = d['mean_s'] / 60
            axs[1].bar(x, mins, w, color=c)
            axs[1].text(x, mins, f'{mins:.1f}', ha='center', va='bottom', fontsize=10)
    axs[0].set_ylim(0.86, 1.0)
    style(axs[0], 'Score (IoU of delivered CAD, 95% CI)')
    axs[1].set_ylim(0, 10.5)
    style(axs[1], 'Minutes per part (mean)')
    fig.legend(*axs[0].get_legend_handles_labels(), frameon=False, loc='lower center', ncol=2, fontsize=11,
               bbox_to_anchor=(0.5, 0.035))
    fig.text(0.5, 0.005, '40 new parts (fresh3: 20 benchA + 20 benchE), 3 episodes each, budget 40 calls / 30 min; '
             'score axis starts at 0.86', ha='center', fontsize=10, color=MUTED)
    fig.tight_layout(rect=(0, 0.1, 1, 1))
    fig.savefig(os.path.join(HERE, 'simple_tools_v3.png'), dpi=220)
    plt.close(fig)


if __name__ == '__main__':
    main()

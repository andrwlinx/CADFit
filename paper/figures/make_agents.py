"""Figures 3 and 4 at paper size (paper/figures/closed.pdf, tools_v3.pdf).

closed.pdf    40 reserved fresh2 parts, 3 episodes: gated IoU of the delivered program (95% CI),
              mean minutes per episode split into model and tool time, API cost per episode.
              Source: results/closed/closed_vs_pipeline.json + episode result.json files.
tools_v3.pdf  40 fresh3 parts, 3 episodes: old (v2) vs new (v3) tools, gated IoU (95% CI) and mean
              minutes per episode. Source: results/tools_v3/tools_v3.json.

  .venv/bin/python paper/figures/make_agents.py
"""
import glob
import json
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
plt.rcParams.update({'font.family': 'serif', 'font.size': 8.5, 'pdf.fonttype': 42})
CODE, SKILLS, OLD, NEW, INK, MUTED = '#eb6834', '#1baf7a', '#6250d6', '#1baf7a', '#0b0b0b', '#52514e'
MODELS = [('sonnet55', 'Sonnet 5.5'), ('opus55', 'Opus 5.5')]


def tidy(ax, title):
    ax.set_title(title, fontsize=9)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED)


def closed():
    c = json.load(open(os.path.join(ROOT, 'results', 'closed', 'closed_vs_pipeline.json')))
    bundle = os.path.join(ROOT, 'results', 'review_bundle_2026-11-05')
    fig, axs = plt.subplots(1, 3, figsize=(7.0, 2.3))
    w = 0.36
    for j, (t, col, lab) in enumerate((('code', CODE, 'code toolset'), ('skills', SKILLS, 'CADFit toolset'))):
        for i, (m, _) in enumerate(MODELS):
            x = i + (j - 0.5) * (w + 0.04)
            a, d = c['arms'][f'{m}/{t}'], c['agent_detail'][f'{m}/{t}']
            axs[0].errorbar(x, a['all'], yerr=[[a['all'] - a['ci95'][0]], [a['ci95'][1] - a['all']]],
                            fmt='o' if t == 'code' else 's', color=col, ecolor=INK, capsize=2, lw=0.8, ms=5,
                            label=lab if i == 0 else None)
            eps = [json.load(open(f)) for tag in ('agentsk_f2', 'agentsk_f2_r1', 'agentsk_f2_r2')
                   for f in glob.glob(os.path.join(bundle, tag, m, t, '*', 'result.json'))]
            model_min = sum(e['seconds_split']['model'] for e in eps) / len(eps) / 60  # recorded model seconds
            mins = d['mean_s'] / 60
            axs[1].bar(x, mins, w, color=col, edgecolor=INK if t == 'skills' else col, lw=0.6)
            axs[1].bar(x, model_min, w, fill=False, hatch='////', edgecolor='white', lw=0)
            axs[1].text(x, mins + 0.15, f'{mins:.1f}', ha='center', fontsize=7)
            axs[2].bar(x, d['cost_per_episode'], w, color=col, edgecolor=INK if t == 'skills' else col, lw=0.6)
            axs[2].text(x, d['cost_per_episode'] + 0.005, f'{d["cost_per_episode"]:.2f}', ha='center', fontsize=7)
    v3 = c['arms']['pipe/v3x3']['all']
    axs[0].axhline(v3, color=MUTED, ls='--', lw=0.8)
    axs[0].text(-0.5, v3 + 0.002, 'optimizer v3', va='bottom', ha='left', fontsize=7, color=MUTED)
    axs[0].set_ylim(0.86, 1.0)
    axs[0].set_ylabel('gated IoU (delivered)')
    axs[1].set_ylabel('minutes per episode')
    axs[1].text(0.03, 0.97, 'hatched: model time', transform=axs[1].transAxes, va='top', fontsize=7, color=MUTED)
    axs[2].set_ylabel('USD per episode')
    for ax, title in zip(axs, ('Score', 'Time', 'API cost')):
        tidy(ax, title)
        ax.set_xticks(range(len(MODELS)), [lab for _, lab in MODELS])
    fig.legend(*axs[0].get_legend_handles_labels(), frameon=False, fontsize=7.5, loc='upper center', ncol=2)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(os.path.join(HERE, 'closed.pdf'))
    fig.savefig(os.path.join(HERE, 'closed.png'), dpi=200)


def tools_v3():
    t = json.load(open(os.path.join(ROOT, 'results', 'tools_v3', 'tools_v3.json')))
    groups = [('opus55', 'code', 'Opus\ncode'), ('opus55', 'skills', 'Opus\nCADFit'),
              ('sonnet55', 'code', 'Sonnet\ncode'), ('sonnet55', 'skills', 'Sonnet\nCADFit')]
    fig, axs = plt.subplots(1, 2, figsize=(7.0, 2.3))
    w = 0.36
    for j, (v, lab) in enumerate((('v2', 'original package'), ('v3', 'revised package'))):
        for i, (m, ts, _) in enumerate(groups):
            x = i + (j - 0.5) * (w + 0.04)
            col = CODE if ts == 'code' else SKILLS
            a, d = t['cells'][f'{m}/{ts}/{v}'], t['detail'][f'{m}/{ts}/{v}']
            axs[0].errorbar(x, a['all'], yerr=[[a['all'] - a['ci95'][0]], [a['ci95'][1] - a['all']]],
                            fmt='o' if ts == 'code' else 's', color=col, mfc=col if v == 'v3' else 'white',
                            ecolor=INK, capsize=2, lw=0.8, ms=5)
            mins = d['mean_s'] / 60
            axs[1].bar(x, mins, w, color=col if v == 'v3' else 'white', edgecolor=col, lw=1.2, hatch=None)
            axs[1].text(x, mins + 0.15, f'{mins:.1f}', ha='center', fontsize=7)
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], marker='o', ls='', color=CODE, label='code toolset'),
               Line2D([], [], marker='s', ls='', color=SKILLS, label='CADFit toolset'),
               Line2D([], [], marker='o', ls='', color=MUTED, mfc='white', label='original package'),
               Line2D([], [], marker='o', ls='', color=MUTED, label='revised package')]
    axs[0].set_ylim(0.86, 1.0)
    axs[0].set_ylabel('gated IoU (delivered)')
    axs[1].set_ylabel('minutes per episode')
    for ax, title in zip(axs, ('Score', 'Time')):
        tidy(ax, title)
        ax.set_xticks(range(len(groups)), [g[2] for g in groups])
    fig.legend(handles=handles, frameon=False, fontsize=7.5, loc='upper center', ncol=4)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(os.path.join(HERE, 'tools_v3.pdf'))
    fig.savefig(os.path.join(HERE, 'tools_v3.png'), dpi=200)


if __name__ == '__main__':
    closed()
    tools_v3()

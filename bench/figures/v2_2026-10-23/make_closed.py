"""Closed models (Claude Opus 5.5, Sonnet 5.5) on the 40 reserved fresh2 parts,
basic coding tools vs CadFit tools, three episodes per part, next to the CadFit pipeline.

  .venv/bin/python bench/figures/v2_2026-10-23/make_closed.py

simple_closed_models.png   score (delivered program, common CAD judge, 95% CI), minutes per
                           episode (model vs tool time), API cost per episode

Inputs: results/closed/closed_vs_pipeline.json (bench/analysis/closed_vs_pipeline.py: every
delivered program re-judged with score.py's CAD replay, iou_cad_gated, averaged over the three
repeats within part; bootstrap over parts within split) and the episodes' result.json files
(seconds_split) under results/review_bundle_2026-11-05/agentsk_f2{,_r1,_r2}.
"""
import glob
import json
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
plt.rcParams.update({'font.family': 'sans-serif', 'font.size': 12})
BASIC, CADFIT = '#eb6834', '#2a78d6'   # validated categorical pair (dataviz palette slots 2, 1)
INK, MUTED = '#0b0b0b', '#52514e'
MODELS = [('sonnet55', 'Sonnet 5.5'), ('opus55', 'Opus 5.5')]
TOOLSETS = [('code', BASIC, 'basic coding tools'), ('skills', CADFIT, 'CadFit tools')]
TAGS = ['agentsk_f2', 'agentsk_f2_r1', 'agentsk_f2_r2']


def load():
    res = json.load(open(os.path.join(ROOT, 'results', 'closed', 'closed_vs_pipeline.json')))
    bundle = os.path.join(ROOT, 'results', 'review_bundle_2026-11-05')
    share = {}
    for m, _ in MODELS:
        for t, _, _ in TOOLSETS:
            eps = [json.load(open(f)) for tag in TAGS
                   for f in glob.glob(os.path.join(bundle, tag, m, t, '*', 'result.json'))]
            share[(m, t)] = (sum(e['seconds_split']['model'] for e in eps)
                             / sum(sum(e['seconds_split'].values()) for e in eps))
    return res, share


def style(ax, title):
    ax.set_title(title, fontsize=13)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED)
    ax.set_xticks(range(len(MODELS)), [lab for _, lab in MODELS])


def main():
    res, model_share = load()
    arms, det = res['arms'], res['agent_detail']
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.4))
    w = 0.36
    for j, (t, c, lab) in enumerate(TOOLSETS):
        for i, (m, _) in enumerate(MODELS):
            x = i + (j - 0.5) * (w + 0.03)
            a, d = arms[f'{m}/{t}'], det[f'{m}/{t}']
            axs[0].bar(x, a['all'], w, color=c, label=lab if i == 0 else None)
            axs[0].errorbar(x, a['all'], yerr=[[a['all'] - a['ci95'][0]], [a['ci95'][1] - a['all']]],
                            color=INK, capsize=3, lw=1)
            axs[0].text(x, a['ci95'][1] + 0.003, f'{a["all"]:.3f}', ha='center', va='bottom', fontsize=10.5)
            minutes = d['mean_s'] / 60
            axs[1].bar(x, minutes, w, color=c)
            axs[1].bar(x, minutes * model_share[(m, t)], w, fill=False, hatch='///', edgecolor='white', lw=0)
            axs[1].text(x, minutes, f'{minutes:.1f}', ha='center', va='bottom', fontsize=10.5)
            axs[2].bar(x, d['cost_per_episode'], w, color=c)
            axs[2].text(x, d['cost_per_episode'], f'${d["cost_per_episode"]:.2f}', ha='center', va='bottom',
                        fontsize=10.5)
    # Pipeline reference on the same 40 parts, same judge (runs without replay failures).
    v = arms['pipe/v3x3']['all']
    axs[0].axhline(v, color=MUTED, ls='--', lw=1.2)
    axs[0].text(1.62, v, f'CadFit\npipeline v3\n{v:.3f}', va='center', ha='left', fontsize=9.5, color=MUTED)
    axs[0].set_ylim(0.85, 1.0)
    axs[0].set_xlim(-0.6, 1.6)
    style(axs[0], 'Score (IoU of delivered CAD, 95% CI)')
    style(axs[1], 'Minutes per part (mean)')
    axs[1].text(0.02, 0.97, 'hatched = waiting on the model\nsolid = running tools (80-92%)',
                transform=axs[1].transAxes, va='top', fontsize=10, color=MUTED)
    axs[1].set_ylim(0, 11)
    style(axs[2], 'API cost per part')
    axs[2].set_ylim(0, 0.32)
    fig.legend(*axs[0].get_legend_handles_labels(), frameon=False, loc='lower center', ncol=2, fontsize=11,
               bbox_to_anchor=(0.5, 0.035))
    fig.text(0.5, 0.005, '40 held-out parts (20 benchA + 20 benchE), 3 episodes each, budget 40 calls / 30 min; '
             'score axis starts at 0.85', ha='center', fontsize=10, color=MUTED)
    fig.tight_layout(rect=(0, 0.1, 1, 1))
    fig.savefig(os.path.join(HERE, 'simple_closed_models.png'), dpi=220)
    plt.close(fig)


if __name__ == '__main__':
    main()

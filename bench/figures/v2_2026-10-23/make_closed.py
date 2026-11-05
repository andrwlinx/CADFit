"""Closed models (Claude Opus 5.5, Sonnet 5.5) on the 40 reserved fresh2 parts,
basic coding tools vs CadFit tools, one episode per part (2026-11-04/05).

  .venv/bin/python bench/figures/v2_2026-10-23/make_closed.py

simple_closed_models.png   validity-gated IoU, minutes per part (model vs tool time), cost per part

Numbers are the per-arm aggregates printed on ORCD from
bench/runs/agentsk_f2/<model>/<toolset>/*/result.json (40 episodes each):
gated IoU = best_iou if best_exec_valid else 0; seconds; seconds_split; cost_usd.
"""
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
plt.rcParams.update({'font.family': 'sans-serif', 'font.size': 12})
BASIC, CADFIT = '#eb6834', '#2a78d6'   # validated categorical pair (dataviz palette slots 2, 1)
INK, MUTED = '#0b0b0b', '#52514e'

MODELS = ['Sonnet 5.5', 'Opus 5.5']
# (gated IoU over 40, mean seconds per part, model share of time, total cost $ over 40)
DATA = {('Sonnet 5.5', 'basic'): (0.8992, 277, 0.22, 6.21), ('Sonnet 5.5', 'cadfit'): (0.8840, 267, 0.15, 4.04),
        ('Opus 5.5', 'basic'): (0.9298, 374, 0.19, 10.59), ('Opus 5.5', 'cadfit'): (0.8849, 515, 0.08, 6.23)}


def bars(ax, value, fmt, title, ylim=None):
    w = 0.36
    for j, (ts, c, lab) in enumerate((('basic', BASIC, 'basic coding tools'), ('cadfit', CADFIT, 'CadFit tools'))):
        for i, m in enumerate(MODELS):
            v = value(DATA[(m, ts)])
            x = i + (j - 0.5) * (w + 0.03)
            ax.bar(x, v, w, color=c, label=lab if i == 0 else None)
            ax.text(x, v, fmt(v), ha='center', va='bottom', fontsize=11, color=INK)
    ax.set_xticks(range(len(MODELS)), MODELS)
    ax.set_title(title, fontsize=13)
    if ylim:
        ax.set_ylim(*ylim)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED)


def main():
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.2))
    bars(axs[0], lambda d: d[0], lambda v: f'{v:.3f}', 'Score (IoU, invalid CAD = 0)', (0, 1.12))
    bars(axs[1], lambda d: d[1] / 60, lambda v: f'{v:.1f}', 'Minutes per part (mean)', (0, 10))
    # Model (API) part of each time bar, hatched; the rest is tool execution.
    w = 0.36
    for j, ts in enumerate(('basic', 'cadfit')):
        for i, m in enumerate(MODELS):
            d = DATA[(m, ts)]
            axs[1].bar(i + (j - 0.5) * (w + 0.03), d[1] / 60 * d[2], w, fill=False, hatch='///',
                       edgecolor='white', lw=0)
    axs[1].text(0.02, 0.97, 'hatched = waiting on the model\nsolid = running tools (78-92%)',
                transform=axs[1].transAxes, va='top', fontsize=10, color=MUTED)
    bars(axs[2], lambda d: d[3] / 40, lambda v: f'${v:.2f}', 'API cost per part', (0, 0.32))
    axs[0].legend(frameon=False, loc='upper left', fontsize=10.5)
    fig.text(0.5, 0.01, '40 held-out parts (20 benchA + 20 benchE), one episode each, '
             'same budget (40 calls, 30 min)', ha='center', fontsize=10, color=MUTED)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(os.path.join(HERE, 'simple_closed_models.png'), dpi=220)
    plt.close(fig)


if __name__ == '__main__':
    main()

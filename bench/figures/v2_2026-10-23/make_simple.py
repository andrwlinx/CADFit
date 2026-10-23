"""Plain-language versions of the v2 figures (2026-10-23 update).

  .venv/bin/python bench/figures/v2_2026-10-23/make_simple.py

simple_pipeline.png   four boxes: find -> run -> check/fix -> deliver
simple_00642725.png   target / before / after with plain labels
simple_00232213.png   same
simple_results.png    two bar pairs: score and broken outputs, old vs v2
"""
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_renders as mr  # noqa: E402

plt.rcParams.update({'font.family': 'sans-serif', 'font.size': 12})
BLUE, RED, GREY = '#1f4e79', '#b5261e', '#999999'


def pipeline():
    fig, ax = plt.subplots(figsize=(10, 2.2))
    ax.set_xlim(0, 10); ax.set_ylim(0, 2); ax.axis('off')
    steps = [('1. Search', 'finds candidate\nCAD programs'),
             ('2. Run', 'build each\nprogram'),
             ('3. Check + fix', 'is the solid valid?\nrepair if not'),
             ('4. Deliver', 'the best program\nthat works')]
    for i, (t, b) in enumerate(steps):
        x = 0.1 + i * 2.5
        ax.add_patch(FancyBboxPatch((x, 0.2), 2.0, 1.6, boxstyle='round,pad=0.02,rounding_size=0.08',
                                    fc='white', ec=BLUE, lw=1.5))
        ax.text(x + 1.0, 1.45, t, ha='center', va='center', fontsize=14, weight='bold')
        ax.text(x + 1.0, 0.75, b, ha='center', va='center', fontsize=11.5)
        if i < 3:
            ax.add_patch(FancyArrowPatch((x + 2.05, 1.0), (x + 2.45, 1.0), arrowstyle='-|>',
                                         mutation_scale=16, lw=1.5, color='black'))
    fig.subplots_adjust(0, 0, 1, 1)
    fig.savefig(os.path.join(HERE, 'simple_pipeline.png'), dpi=220)
    plt.close(fig)


def example(part, before, after, before_label, after_label, ious, out):
    import glob

    import numpy as np
    import trimesh
    gt_stl = glob.glob(os.path.join(mr.ROOT, 'bench', 'cadbench', 'fresh', f'{part}_*.stl'))[0]
    gt = mr.iou.normalize_mesh(trimesh.load(gt_stl, force='mesh'))
    if len(gt.faces) > 60_000:
        gt = gt.simplify_quadric_decimation(face_count=60_000)
    lim = (gt.bounds[0], gt.bounds[1])
    fig = plt.figure(figsize=(10, 3.4))
    ax = fig.add_subplot(1, 3, 1, projection='3d')
    mr.draw(ax, [gt], [mr.GREY], 'Target shape', (24, -60), lim)
    for k, (path, label, j) in enumerate(zip((before, after), (before_label, after_label), ious)):
        parts = mr.program_meshes(os.path.join(mr.IN, path))
        ms = [m for m, _ in parts if m is not None]
        cs = [mr.BLUE if ok else mr.RED for m, ok in parts if m is not None]
        ok = all(v for _, v in parts)
        ax = fig.add_subplot(1, 3, k + 2, projection='3d')
        mr.draw(ax, ms, cs, label, (24, -60), lim)
        ax.text2D(0.5, -0.02, f'score {j if ok else 0.0:.2f}' + ('' if ok else '  (broken, counts as 0)'),
                  transform=ax.transAxes, ha='center', fontsize=12, color=BLUE if ok else RED, weight='bold')
    fig.text(0.01, 0.02, 'red = broken piece', fontsize=10, color=RED)
    fig.subplots_adjust(left=0, right=1, top=0.88, bottom=0.08, wspace=0)
    fig.savefig(os.path.join(HERE, out), dpi=220)
    plt.close(fig)


def results():
    # dev4 run, 60 dev parts (dev34_scores.json): dev3_d0 vs dev4_v2.
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4))
    ax = axes[0]
    ax.bar(['Old', 'v2'], [0.808, 0.949], color=[GREY, BLUE], width=0.55)
    for x, v in enumerate([0.808, 0.949]):
        ax.text(x, v + 0.01, f'{v:.2f}', ha='center', fontsize=14, weight='bold')
    ax.set_ylim(0.6, 1.0); ax.set_title('Average score (higher is better)', fontsize=13)
    ax = axes[1]
    ax.bar(['Old', 'v2'], [8, 1], color=[GREY, BLUE], width=0.55)
    for x, v in enumerate([8, 1]):
        ax.text(x, v + 0.2, f'{v} of 60', ha='center', fontsize=14, weight='bold')
    ax.set_ylim(0, 10); ax.set_title('Broken or missing outputs (lower is better)', fontsize=13)
    for a in axes:
        a.spines[['top', 'right']].set_visible(False)
        a.tick_params(labelsize=13)
        a.set_yticks([])
        a.spines['left'].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, 'simple_results.png'), dpi=220)
    plt.close(fig)


if __name__ == '__main__' and len(sys.argv) == 1:
    pipeline()
    results()
    example('00642725', '00642725_search.py', '00642725_v2.py',
            'Before: 208 overlapping pieces', 'After: merged into 1 solid',
            [0.000898, 0.937546], 'simple_00642725.png')
    example('00232213', '00232213_orig.py', '00232213_repair.py',
            'Before: 2 broken pieces', 'After: repaired',
            [0.872512, 0.872512], 'simple_00232213.png')
    print('done')


def open_models():
    # 20 parts, pre-v2 tools (paper/numbers.tex: m*Code / m*Skills, agentPipeSec).
    from matplotlib.patches import Patch
    rows = [('Gemma-4-31B', 0.593, 0.892), ('Qwen3.6-35B', 0.465, 0.854), ('gpt-oss-120b', 0.557, 0.812),
            ('Devstral-24B', 0.305, 0.776), ('gpt-oss-20b', 0.422, 0.732), ('Qwen3.8-27B', 0.307, 0.730)]
    fmt = lambda v: f'{v + 1e-9:.2f}'  # 0.305 -> 0.31, as the slide text rounds
    fig, ax = plt.subplots(figsize=(9, 4.4))
    y = list(range(len(rows)))[::-1]
    for yi, (name, code, ours) in zip(y, rows):
        ax.barh(yi + 0.2, code, height=0.38, color=GREY)
        ax.barh(yi - 0.2, ours, height=0.38, color=BLUE)
        ax.text(code - 0.01, yi + 0.2, fmt(code), va='center', ha='right', fontsize=11, color='white', weight='bold')
        ax.text(ours - 0.01, yi - 0.2, fmt(ours), va='center', ha='right', fontsize=11, color='white', weight='bold')
    ax.set_yticks(y, [r[0] for r in rows], fontsize=12)
    ax.axvline(0.904, color='black', lw=1, ls='--')
    ax.text(0.915, -0.45, 'our pipeline\n0.90', fontsize=10.5, va='bottom')
    ax.set_xlim(0, 1.08); ax.set_xticks([])
    ax.spines[['top', 'right', 'bottom']].set_visible(False)
    ax.legend(handles=[Patch(color=GREY, label='basic coding tools'), Patch(color=BLUE, label='CADFit tools')],
              loc='lower center', bbox_to_anchor=(0.5, 1.0), ncol=2, frameon=False, fontsize=12)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, 'simple_open_models.png'), dpi=220)
    plt.close(fig)


if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == 'open_models':
    open_models()

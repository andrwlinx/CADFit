"""CADFit++ v2 pipeline diagram: search proposes programs, delivery executes them.

  .venv/bin/python bench/figures/v2_2026-10-23/make_diagram.py
"""
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = os.path.dirname(os.path.abspath(__file__))
plt.rcParams.update({'font.family': 'serif', 'font.size': 8.5})
INK, BLUE, PALE, RED, GREEN = '#222222', '#1f4e79', '#dbe7f3', '#b5261e', '#2e7d32'


def box(ax, x, y, w, h, title, body, face=PALE, edge=BLUE):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.02,rounding_size=0.06',
                                fc=face, ec=edge, lw=1.1))
    ax.text(x + w / 2, y + h - 0.13, title, ha='center', va='top', fontsize=9, weight='bold', color=INK)
    ax.text(x + w / 2, y + h - 0.42, body, ha='center', va='top', fontsize=7.6, color=INK, linespacing=1.35)


def arrow(ax, a, b, color=INK, text=None, dy=0.08):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle='-|>', mutation_scale=10, lw=1.0, color=color))
    if text:
        ax.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + dy, text, ha='center', va='bottom', fontsize=7, color=color)


fig, ax = plt.subplots(figsize=(7.4, 3.0))
ax.set_xlim(0, 10.4); ax.set_ylim(0, 4.22); ax.axis('off')

# Row 1: search (unchanged CADFit++ search, original-mesh sections in v2)
ax.text(0.05, 4.1, 'Search (proposes programs)', fontsize=8, color=BLUE, style='italic', va='top')
box(ax, 0.05, 2.45, 1.75, 1.45, 'Input mesh', 'STL / scan\n(GT for scoring:\nCADBench solid)', face='#eeeeee', edge='#777777')
box(ax, 2.15, 2.45, 2.3, 1.45, 'Primitive proposals', 'planar sections -> extrudes\nrevolve axes (checked\nagainst the axis at emit)\nsweeps, lofts, fillets')
box(ax, 4.8, 2.45, 2.3, 1.45, 'Greedy / beam search', 'union / cut candidates\nscored by mesh IoU\n+ residual refinement')
arrow(ax, (1.8, 3.17), (2.15, 3.17))
arrow(ax, (4.45, 3.17), (4.8, 3.17))

# Row 2: execution-verified delivery (new in v2)
ax.text(6.3, 2.3, 'Execution-verified delivery (new in v2)', fontsize=8, color=RED, style='italic', va='center')
box(ax, 0.05, 0.1, 2.35, 1.6, 'Program variants', 'original (search output)\nfused: .add() -> OCC fuse\nfailed cuts skipped\ntop-3 single candidates\nbest section candidate',
    face='#fbe9e7', edge=RED)
box(ax, 2.75, 0.1, 2.3, 1.6, 'Execute + check', 'run each in CadQuery\nOCC BRepCheck per solid\nrepair: ShapeFix each\ninvalid solid, drop if\nstill invalid -> *_repair',
    face='#fbe9e7', edge=RED)
box(ax, 5.4, 0.1, 2.15, 1.6, 'Judge', 'IoU of the executed\nprogram vs the input\n(exact boolean, or\nwinding-number MC when\neither side is open)',
    face='#fbe9e7', edge=RED)
box(ax, 7.9, 0.1, 2.4, 1.6, 'Deliver', 'best VALID program\n(valid-first, then IoU);\nif none is valid: best\nbuilt one, flagged and\nscored as gated 0',
    face='#e8f5e9', edge=GREEN)
arrow(ax, (5.95, 2.45), (1.2, 1.7), color=RED, text='programs', dy=0.02)
arrow(ax, (2.4, 0.9), (2.75, 0.9), color=RED)
arrow(ax, (5.05, 0.9), (5.4, 0.9), color=RED)
arrow(ax, (7.55, 0.9), (7.9, 0.9), color=RED)

# Metric note
ax.text(7.45, 3.85, 'Reported metric', fontsize=8.5, weight='bold', va='top', color=INK)
ax.text(7.45, 3.55, 'validity-gated IoU(CAD):\nIoU of the delivered program,\n0 if it does not build or any\nsolid fails OCC validity.\n(mesh IoU can hide both)',
        fontsize=7.6, va='top', color=INK, linespacing=1.35)

fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
for ext in ('png', 'pdf'):
    fig.savefig(os.path.join(HERE, f'pipeline_v2.{ext}'), dpi=220)
print('pipeline_v2')

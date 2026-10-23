"""Before/after renders for the v2 update (2026-10-23).

  .venv/bin/python bench/figures/v2_2026-10-23/make_renders.py

Each program in inputs/ is executed, every solid is checked with OCC
(BRepCheck via Shape.isValid) and tessellated; invalid solids are drawn red.
IoUs are the ones the pipeline recorded for these programs (exec_verify
records: dev2_v2/00642725 final_iou.json; dev4_v2/00232213 final_iou.json),
not recomputed here: judging the 208-solid soup against the 24 MB GT takes
longer than the figure is worth.

  00642725: the search program (dev2_v2 best_greedy_parallel.py) stacks
            overlapping solids with `.add()`: 208 solids, 34 OCC-invalid, as in
            its exec_verify record. v2's execution check delivers the fused
            rewrite (best_greedy_parallel_iterative.py), one valid solid.
  00232213: the search program has invalid solids; v2's repair pass
            (ShapeFix per invalid solid, drop it if still invalid) delivers a
            valid program with the same geometry.
"""
import glob
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, ROOT)
import cadquery as cq  # noqa: E402
import iou  # noqa: E402

IN = os.path.join(HERE, 'inputs')
BLUE, RED, GREY = np.array([0.13, 0.32, 0.50]), np.array([0.80, 0.15, 0.12]), np.array([0.62, 0.62, 0.62])
plt.rcParams.update({'font.family': 'serif', 'font.size': 9})


def run_program(path):
    src = '\n'.join(l for l in open(path).read().splitlines() if 'exporters.export' not in l)
    ns = {'__name__': '__main__'}
    exec(compile(src, path, 'exec'), ns)
    shapes = ns['result'].vals()
    solids = [s for sh in shapes for s in sh.Solids()]
    return solids


def tess(shape, tol=2e-3):
    v, f = shape.tessellate(tol, 0.3)
    return trimesh.Trimesh(np.array([p.toTuple() for p in v]), np.array(f), process=False)


def program_meshes(path):
    """[(mesh, valid)] per solid, plus the whole program as one STL for judging."""
    out = []
    for s in run_program(path):
        try:
            out.append((tess(s), bool(s.isValid())))
        except Exception:
            out.append((None, False))
    return out


def draw(ax, meshes, colors, title, view=(22, -58), lim=None):
    for m, c in zip(meshes, colors):
        tri = m.vertices[m.faces]
        n = m.face_normals
        light = np.array([0.4, -0.5, 0.75]) / np.linalg.norm([0.4, -0.5, 0.75])
        shade = 0.45 + 0.55 * np.clip(np.abs(n @ light), 0, 1)
        fc = np.clip(c[None, :] * shade[:, None] + 0.25 * (1 - shade[:, None]), 0, 1)
        ax.add_collection3d(Poly3DCollection(tri, facecolors=fc, edgecolors='none', linewidths=0))
    lo, hi = lim
    c, r = (lo + hi) / 2, (hi - lo).max() / 2
    ax.set_xlim(c[0] - r, c[0] + r); ax.set_ylim(c[1] - r, c[1] + r); ax.set_zlim(c[2] - r, c[2] + r)
    ax.set_box_aspect((1, 1, 1), zoom=1.4)
    ax.view_init(*view)
    ax.set_axis_off()
    ax.set_title(title, fontsize=9, pad=-2)


def figure(part, before, after, labels, ious, out, view):
    gt_stl = glob.glob(os.path.join(ROOT, 'bench', 'cadbench', 'fresh', f'{part}_*.stl'))[0]
    gt = iou.normalize_mesh(trimesh.load(gt_stl, force='mesh'))
    if len(gt.faces) > 60_000:
        gt = gt.simplify_quadric_decimation(face_count=60_000)
    rows = []
    for path, j in zip((before, after), ious):
        rows.append((program_meshes(os.path.join(IN, path)), j))
    lim = (gt.bounds[0], gt.bounds[1])
    fig = plt.figure(figsize=(7.2, 2.6))
    ax = fig.add_subplot(1, 3, 1, projection='3d')
    draw(ax, [gt], [GREY], 'target mesh', view, lim)
    for k, ((parts, j), lab) in enumerate(zip(rows, labels)):
        ms = [m for m, _ in parts if m is not None]
        cs = [BLUE if ok else RED for m, ok in parts if m is not None]
        n_bad = sum(not ok for _, ok in parts)
        valid = n_bad == 0
        gated = j if valid else 0.0
        ax = fig.add_subplot(1, 3, k + 2, projection='3d')
        draw(ax, ms, cs, f'{lab}\n{len(parts)} solid{"s" if len(parts) != 1 else ""}, '
                         f'{n_bad} OCC-invalid', view, lim)
        ax.text2D(0.5, -0.04, f'IoU {j:.3f}  ->  validity-gated {gated:.3f}', transform=ax.transAxes,
                  ha='center', fontsize=8.5, color=RED if not valid else BLUE)
    fig.text(0.005, 0.02, 'red: OCC-invalid solid (BRepCheck)', ha='left', fontsize=7, color=RED)
    fig.subplots_adjust(left=0, right=1, top=0.86, bottom=0.08, wspace=0)
    for ext in ('png', 'pdf'):
        fig.savefig(os.path.join(HERE, f'{out}.{ext}'), dpi=220)
    plt.close(fig)
    print(out, [(len(p), sum(not ok for _, ok in p), round(j, 4)) for p, j in rows])


if __name__ == '__main__':
    figure('00642725', '00642725_search.py', '00642725_v2.py',
           ['search program (.add of solids)', 'v2: fused rewrite (exec-verified)'],
           [0.000898, 0.937546],
           'render_00642725_fuse', view=(24, -60))
    figure('00232213', '00232213_orig.py', '00232213_repair.py',
           ['search program', 'v2: repair pass'],
           [0.872512, 0.872512],
           'render_00232213_repair', view=(24, -60))

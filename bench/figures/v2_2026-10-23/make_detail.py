"""Input mesh -> broken CAD -> fixed CAD -> detail map (2026-10-23 update).

  .venv/bin/python bench/figures/v2_2026-10-23/make_detail.py

The detail map colors the input mesh by its distance to the delivered CAD
(normalized frame: the part's largest extent spans [-1, 1], so 0.01 is 0.5% of
the part size). Distances are to dense surface samples of the CAD (KD-tree),
so they are accurate to about the sample spacing (~0.001).

Numbers per part (detail.json):
  within_1pct   share of the input surface within 0.02 (1% of the part size) of the CAD
  within_half   same at 0.01 (0.5%)
  chamfer       mean of the two one-sided mean distances
  max_miss      95th percentile distance from the input surface to the CAD
"""
import glob
import json
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from matplotlib.colors import LinearSegmentedColormap
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_renders as mr  # noqa: E402

plt.rcParams.update({'font.family': 'sans-serif', 'font.size': 12})
BLUE, RED = '#1f4e79', '#b5261e'
TAU = 0.02          # 1% of the part size (extent 2)
CAD_SAMPLES = 3_000_000  # spacing ~0.001, well under TAU / 2
CMAP = LinearSegmentedColormap.from_list('miss', ['#d9d9d9', '#f4a582', RED])


def gt_mesh(part):
    stl = glob.glob(os.path.join(mr.ROOT, 'bench', 'cadbench', 'fresh', f'{part}_*.stl'))[0]
    gt = mr.iou.normalize_mesh(trimesh.load(stl, force='mesh'))
    if len(gt.faces) > 60_000:
        gt = gt.simplify_quadric_decimation(face_count=60_000)
    return gt


def stats(gt, cad):
    np.random.seed(0)
    g = gt.sample(100_000)
    c = cad.sample(CAD_SAMPLES)
    d_gc = cKDTree(c).query(g)[0]   # input surface -> CAD: missing detail
    d_cg = cKDTree(g).query(c)[0]   # CAD -> input surface: extra material
    return {'within_1pct': float((d_gc <= TAU).mean()), 'within_half': float((d_gc <= TAU / 2).mean()),
            'chamfer': float((d_gc.mean() + d_cg.mean()) / 2), 'p95_miss': float(np.percentile(d_gc, 95))}


def draw_mesh(ax, m, fc, title, lim, edges=False):
    tri = m.vertices[m.faces]
    ax.add_collection3d(Poly3DCollection(tri, facecolors=fc, edgecolors=(0, 0, 0, 0.25) if edges else 'none',
                                         linewidths=0.15 if edges else 0))
    lo, hi = lim
    c, r = (lo + hi) / 2, (hi - lo).max() / 2
    ax.set_xlim(c[0] - r, c[0] + r); ax.set_ylim(c[1] - r, c[1] + r); ax.set_zlim(c[2] - r, c[2] + r)
    ax.set_box_aspect((1, 1, 1), zoom=1.4)
    ax.view_init(24, -60)
    ax.set_axis_off()
    ax.set_title(title, fontsize=13, pad=-2)


def shade(m, rgb):
    light = np.array([0.4, -0.5, 0.75]) / np.linalg.norm([0.4, -0.5, 0.75])
    s = 0.45 + 0.55 * np.clip(np.abs(m.face_normals @ light), 0, 1)
    rgb = np.atleast_2d(rgb)
    return np.clip(rgb * s[:, None] + 0.25 * (1 - s[:, None]), 0, 1)


def figure(part, before, after, before_label, after_label, ious, out):
    gt = gt_mesh(part)
    lim = (gt.bounds[0], gt.bounds[1])
    fig = plt.figure(figsize=(13, 3.6))

    # 1. Input mesh, with its triangles visible.
    small = gt.simplify_quadric_decimation(face_count=6000) if len(gt.faces) > 6000 else gt
    ax = fig.add_subplot(1, 4, 1, projection='3d')
    draw_mesh(ax, small, shade(small, mr.GREY), 'Input mesh', lim, edges=True)
    ax.text2D(0.5, -0.02, f'{len(gt.faces):,} triangles' if len(gt.faces) < 60_000 else 'triangle mesh',
              transform=ax.transAxes, ha='center', fontsize=11)

    # 2-3. Broken CAD, fixed CAD.
    fixed = None
    for k, (path, label, j) in enumerate(zip((before, after), (before_label, after_label), ious)):
        parts = mr.program_meshes(os.path.join(mr.IN, path))
        ms = [m for m, _ in parts if m is not None]
        cs = [mr.BLUE if ok else mr.RED for m, ok in parts if m is not None]
        ok = all(v for _, v in parts)
        ax = fig.add_subplot(1, 4, k + 2, projection='3d')
        mr.draw(ax, ms, cs, '', (24, -60), lim)
        ax.set_title(label, fontsize=13, pad=-2)
        ax.text2D(0.5, -0.02, f'score {j if ok else 0.0:.2f}' + ('' if ok else ' (red = broken piece)'),
                  transform=ax.transAxes, ha='center', fontsize=12, color=BLUE if ok else RED, weight='bold')
        if k == 1:
            fixed = trimesh.util.concatenate(ms)

    # 4. Detail map: input mesh colored by distance to the fixed CAD.
    st = stats(gt, fixed)
    # Long sliver triangles would get one color for their whole length: split them first.
    fine = trimesh.Trimesh(*trimesh.remesh.subdivide_to_size(gt.vertices, gt.faces, max_edge=0.04, max_iter=8))
    d = cKDTree(fixed.sample(CAD_SAMPLES)).query(fine.triangles_center)[0]
    col = CMAP(np.clip(d / TAU, 0, 1))[:, :3]
    ax = fig.add_subplot(1, 4, 4, projection='3d')
    draw_mesh(ax, fine, shade(fine, np.array([1, 1, 1])) * col, 'Detail recovered', lim)
    ax.text2D(0.5, -0.02, f'{st["within_half"] * 100:.0f}% within 0.5% of part size',
              transform=ax.transAxes, ha='center', fontsize=11, weight='bold', color=BLUE)
    fig.text(0.875, 0.005, 'grey = matched, red = off by 1%+', fontsize=10, color=RED, ha='center')
    fig.subplots_adjust(left=0, right=1, top=0.88, bottom=0.08, wspace=0)
    fig.savefig(os.path.join(HERE, out + '.png'), dpi=200)
    plt.close(fig)
    return st


if __name__ == '__main__':
    res = {}
    res['00642725'] = figure('00642725', '00642725_search.py', '00642725_v2.py',
                             'Broken CAD (old)', 'Fixed CAD (new)', [0.000898, 0.937546], 'detail_00642725')
    res['00232213'] = figure('00232213', '00232213_orig.py', '00232213_repair.py',
                             'Broken CAD (old)', 'Fixed CAD (new)', [0.872512, 0.872512], 'detail_00232213')
    json.dump(res, open(os.path.join(HERE, 'detail.json'), 'w'), indent=1)
    print(json.dumps(res, indent=1))

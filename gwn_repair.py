"""Winding-number repair of open input meshes.

Raw ABC meshes are mostly open triangle soups (not fixable by vertex merge;
some are 1e5 disconnected triangles). Their solid is only defined by the
generalized winding number (GWN), which is what bench/score.py's soup judge
uses. The pipeline's own closed surrogate (direct manifold conversion, or
alpha-wrap of the decimated mesh) can be far off: 0.33x the GWN volume on
00001945, 1.86x on 00000014, nothing at all on 00001576. The search then
optimizes against the wrong target.

`repair_to_winding_solid` writes a watertight mesh whose inside is
GWN >= 0.5: the GWN is evaluated on a grid (exactly in a narrow band around
the surface, from a coarse grid elsewhere), the surface is extracted with
manifold3d's level_set, and the result is snapped to the source bounding box
so the pipeline's bounds-based normalization frame is unchanged.
"""
import os
import time

import numpy as np
import trimesh
from scipy.spatial import cKDTree


def _gwn_tri(T, q):
    """Exact winding-number contribution of triangles T (k,3,3) at points q (m,3)."""
    import numpy as np
    a = T[None, :, 0, :] - q[:, None, :]
    b = T[None, :, 1, :] - q[:, None, :]
    c = T[None, :, 2, :] - q[:, None, :]
    la, lb, lc = (np.linalg.norm(x, axis=2) for x in (a, b, c))
    det = np.einsum('ijk,ijk->ij', a, np.cross(b, c))
    den = (la * lb * lc + np.einsum('ijk,ijk->ij', a, b) * lc
           + np.einsum('ijk,ijk->ij', b, c) * la + np.einsum('ijk,ijk->ij', c, a) * lb)
    return (2 * np.arctan2(det, den)).sum(1) / (4 * np.pi)


def _gwn_fast(mesh, Q, leaf=128, beta=2.5, chunk=4000):
    """Generalized winding number with a one-level far-field approximation
    (Barill et al. 2018): triangles are grouped into spatially coherent
    clusters (Morton order of centroids); a cluster farther than beta times
    its radius contributes its area-weighted dipole, nearer ones are summed
    exactly. For meshes of 1e5-1e6 faces this is orders of magnitude faster
    than _gwn, and still tolerant of triangle soups."""
    import numpy as np
    T = np.asarray(mesh.triangles, dtype=np.float64)
    cen = T.mean(1)
    lo, hi = cen.min(0), cen.max(0)
    g = np.clip(((cen - lo) / np.maximum(hi - lo, 1e-12) * 1023).astype(np.int64), 0, 1023)

    def spread(x):
        x = (x | (x << 16)) & 0x030000FF
        x = (x | (x << 8)) & 0x0300F00F
        x = (x | (x << 4)) & 0x030C30C3
        return (x | (x << 2)) & 0x09249249
    T = T[np.argsort(spread(g[:, 0]) | (spread(g[:, 1]) << 1) | (spread(g[:, 2]) << 2), kind='stable')]
    K = (len(T) + leaf - 1) // leaf
    starts = np.arange(K) * leaf
    an = 0.5 * np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])          # area * unit normal
    area = np.linalg.norm(an, axis=1)
    cen = T.mean(1)
    D = np.add.reduceat(an, starts)                                       # cluster dipoles
    w = np.add.reduceat(area, starts)
    C = np.add.reduceat(cen * area[:, None], starts) / np.maximum(w, 1e-30)[:, None]
    seg = np.repeat(np.arange(K), leaf)[:len(T)]
    R = np.zeros(K)
    np.maximum.at(R, seg, np.linalg.norm(T - C[seg][:, None, :], axis=2).max(1))
    out = np.zeros(len(Q))
    for s in range(0, len(Q), chunk):
        q = Q[s:s + chunk]
        d = C[None, :, :] - q[:, None, :]                                 # (m,K,3)
        r = np.linalg.norm(d, axis=2)
        near = r <= beta * R[None, :]
        far = np.einsum('mkj,kj->mk', d, D) / np.maximum(r, 1e-30) ** 3
        far[near] = 0.0
        acc = far.sum(1) / (4 * np.pi)
        for k in np.nonzero(near.any(0))[0]:
            idx = np.nonzero(near[:, k])[0]
            acc[idx] += _gwn_tri(T[starts[k]:starts[k] + leaf], q[idx])
        out[s:s + chunk] = acc
    return out


def _winding_grid(mesh, h, levels=2, leaf=32, max_surface_samples=2_000_000):
    """GWN on a grid of spacing h over the padded bounding box, built coarse
    to fine: the coarsest grid (spacing h * 2**levels) is evaluated
    everywhere; on each finer grid only nodes near the surface are evaluated,
    and the rest copy their nearest parent node. A parent node lies within
    (sqrt3/2) * parent spacing = sqrt3 * spacing of the child, so a child
    farther than that (plus the surface-sample spacing, which bounds the
    error of the distance estimate) from the surface is on the parent's side.
    leaf=32 halves the GWN cost over the judge's default with no label
    changes on 16k near-surface test points (00001945, 00000014)."""
    lo, hi = mesh.bounds[0] - 2 * h, mesh.bounds[1] + 2 * h
    n_s = int(min(max_surface_samples, max(50_000, mesh.area / (0.5 * h) ** 2)))
    S, _ = trimesh.sample.sample_surface(mesh, n_s, seed=0)
    spacing = float(np.sqrt(mesh.area / n_s))
    tree = cKDTree(S)

    w = shape = None
    stats = {'exact': 0}
    for k in range(levels, -1, -1):
        hk = h * 2 ** k
        axes = [np.arange(lo[i], hi[i] + hk, hk) for i in range(3)]
        new_shape = tuple(len(a) for a in axes)
        P = np.stack(np.meshgrid(*axes, indexing='ij'), -1).reshape(-1, 3)
        if w is None:
            wk = _gwn_fast(mesh, P, leaf=leaf)
            stats['exact'] += len(P)
        else:
            near = tree.query(P, k=1, workers=-1)[0] < np.sqrt(3) * hk + spacing + 0.1 * hk
            idx = np.stack([np.clip(np.rint((P[:, i] - lo[i]) / (2 * hk)).astype(int), 0, shape[i] - 1)
                            for i in range(3)], 1)
            wk = w.ravel()[np.ravel_multi_index(idx.T, shape)]
            wk[near] = _gwn_fast(mesh, P[near], leaf=leaf)
            stats['exact'] += int(near.sum())
        w, shape = wk.reshape(new_shape), new_shape
    stats['fine'] = int(np.prod(shape))
    return w, lo, stats


def _solid_from_grid(w, lo, h, ref_bounds):
    import manifold3d
    nx, ny, nz = w.shape

    def f(x, y, z):  # trilinear GWN - 0.5 (positive inside)
        gx, gy, gz = (x - lo[0]) / h, (y - lo[1]) / h, (z - lo[2]) / h
        i, j, k = int(gx), int(gy), int(gz)
        if i < 0 or j < 0 or k < 0 or i >= nx - 1 or j >= ny - 1 or k >= nz - 1:
            return -0.5
        fx, fy, fz = gx - i, gy - j, gz - k
        c = w[i:i + 2, j:j + 2, k:k + 2]
        c = c[0] * (1 - fx) + c[1] * fx
        c = c[0] * (1 - fy) + c[1] * fy
        return c[0] * (1 - fz) + c[1] * fz - 0.5

    hi = lo + h * (np.array(w.shape) - 1)
    M = manifold3d.Manifold.level_set(f, [*lo, *hi], h)
    # A soup's GWN leaves specks of solid around stray triangles (00001576:
    # 93 bodies of <0.2% beside one of 0.025); multi-body meshes are
    # alpha-wrapped by iou._cached_manifold, so drop the specks. Subtract
    # them rather than re-adding the kept bodies: decompose() also returns
    # each internal cavity as a negative-volume shell, and adding that back
    # fills the cavity (00000648: volume 0.79e8 -> 1.55e8).
    bodies = M.decompose()
    total = sum(b.volume() for b in bodies if b.volume() > 0)
    specks = [b for b in bodies if 0 < b.volume() < 1e-2 * total]
    if specks:
        M = M - (manifold3d.Manifold.batch_boolean(specks, manifold3d.OpType.Add)
                 if len(specks) > 1 else specks[0])
    m = M.to_mesh()
    V = np.asarray(m.vert_properties)[:, :3].astype(float)
    F = np.asarray(m.tri_verts).astype(np.int64)
    # level_set is manifold by index, but where two sheets of a thin part
    # meet within a cell distinct vertices share a position; an STL (which
    # stores positions only) then reloads with edges used 4 times and
    # trimesh/iou reject it as non-watertight. Pull each copy of a shared
    # position a hair (1e-3 cell) toward its own incident faces.
    _, inv, cnt = np.unique(V.astype(np.float32), axis=0, return_inverse=True, return_counts=True)
    dup = cnt[inv.ravel()] > 1
    if dup.any():
        cen = V[F].mean(1)
        acc = np.zeros_like(V)
        n = np.zeros(len(V))
        for k in range(3):
            np.add.at(acc, F[:, k], cen)
            np.add.at(n, F[:, k], 1)
        d = acc[dup] / np.maximum(n[dup], 1)[:, None] - V[dup]
        V[dup] += 1e-3 * h * d / np.maximum(np.linalg.norm(d, axis=1), 1e-30)[:, None]
    tm = trimesh.Trimesh(V, F, process=False)
    # Sub-cell stretch onto the source bounds keeps the normalization identical.
    # Beyond that the solid is not the soup's bounding box (open sheets or
    # stray triangles at the edges enclose no volume) and stretching distorts
    # it: 00002336's solid was pulled 0.3 of its height down, IoU 0.23 vs the
    # judge. Its bounds-based frame would differ from the judge's, so decline.
    b0, b1 = tm.bounds
    r0, r1 = ref_bounds
    gap = max(np.abs(b0 - r0).max(), np.abs(b1 - r1).max())
    if gap > 1.5 * h:
        print(f"⚠️  Winding-number solid's bounds are {gap / h:.1f} cells inside the input's; not repairing")
        return None
    s = np.where(b1 - b0 > 1e-12, (r1 - r0) / np.maximum(b1 - b0, 1e-12), 1.0)
    tm.vertices = (tm.vertices - b0) * s + r0
    return tm


def repair_to_winding_solid(stl_path, out_path, cells_on_max_extent=128, cells_across_thickness=3,
                            n_volume_samples=20_000, seed=0):
    """Write the GWN solid of `stl_path` to `out_path` (reused if present) and
    return out_path, or None if no non-empty watertight solid came out.

    Grid spacing: max extent / `cells_on_max_extent`, refined to a third of
    the estimated plate thickness 2V/A for thin parts (V from a GWN Monte
    Carlo estimate over the bounding box), but never finer than extent/512."""
    if os.path.exists(out_path):
        return out_path
    declined = out_path + '.declined'
    if os.path.exists(declined):
        return None
    t0 = time.time()
    mesh = trimesh.load(stl_path, force='mesh')
    lo, hi = mesh.bounds
    ext = (hi - lo).max()
    Q = np.random.default_rng(seed).uniform(lo, hi, (n_volume_samples, 3))
    vol = (_gwn_fast(mesh, Q, leaf=32) > 0.5).mean() * np.prod(hi - lo)
    t = 2 * vol / max(mesh.area, 1e-12)
    h = float(min(ext / cells_on_max_extent, max(t / cells_across_thickness, ext / 512)))
    w, glo, stats = _winding_grid(mesh, h)
    solid = _solid_from_grid(w, glo, h, mesh.bounds)
    if solid is None:
        open(declined, 'w').close()
        return None
    if not solid.is_watertight or solid.volume <= 0:
        print(f"⚠️  Winding-number repair produced no valid solid for {stl_path}")
        return None
    tmp = out_path + '.tmp.stl'
    solid.export(tmp)
    os.replace(tmp, out_path)
    print(f"✓ Winding-number solid → {out_path} (h={h:.4g}, {stats['exact']:,} exact of {stats['fine']:,} "
          f"grid nodes, vol {solid.volume:.4g} vs MC {vol:.4g}, {time.time() - t0:.0f}s)")
    return out_path

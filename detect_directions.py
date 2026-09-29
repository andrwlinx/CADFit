#!/usr/bin/env python3
"""
Detect candidate extrusion directions from the Gauss map of a mesh.

The side walls of a prism extruded along d have normals perpendicular to d, so
they lie on the great circle whose pole is d. Face normals are grouped into
clusters (area-weighted); every pair of non-parallel clusters proposes its
cross product as d, and d is scored by the area of all clusters perpendicular
to it. Requiring several distinct wall clusters (or curved walls) keeps a lone
large plane, whose own great circle is uniformly supported, from producing
arbitrary peaks. Each winner is refined as the smallest eigenvector of the
normal covariance of its inlier faces (the Point2Cyl closed form).

Stock CADFit only slices along X/Y/Z plus the normals of detected planar
faces, so an oblique prism without a clean planar cap (or whose cap was lost
to the 100-entry subsample) is never proposed. Directions already covered by
X/Y/Z or by a large planar cap are dropped.

Usage:
  python detect_directions.py mesh.stl [--out directions.json]
"""
import argparse
import json

import numpy as np
import trimesh


def _canon(d):
    d = d / np.linalg.norm(d)
    k = np.argmax(np.abs(d))
    return d if d[k] > 0 else -d


def normal_clusters(normals, areas, tol_deg=3.0, max_clusters=300):
    """Greedy area-ordered clustering of normals up to sign. Returns (dirs, area, members)."""
    cos_t = np.cos(np.radians(tol_deg))
    unassigned = np.ones(len(normals), bool)
    order = np.argsort(-areas)
    dirs, cl_area, members = [], [], []
    for i in order:
        if not unassigned[i]:
            continue
        m = unassigned & (np.abs(normals @ normals[i]) > cos_t)
        dirs.append(normals[i])
        cl_area.append(areas[m].sum())
        members.append(np.flatnonzero(m))
        unassigned &= ~m
        if len(dirs) >= max_clusters or not unassigned.any():
            break
    return np.array(dirs), np.array(cl_area), members


def detect_directions(mesh, max_dirs=6, perp_tol_deg=2.0, nms_deg=5.0, min_frac=0.08,
                      min_walls=3, top_pairs=40, cap_frac=0.01, exclude_deg=3.0):
    """Return a list of {'direction', 'support', 'walls'} sorted by support.

    support: fraction of total area whose normal is perpendicular to d.
    walls:   number of distinct normal clusters perpendicular to d.
    """
    with np.errstate(all='ignore'):
        normals = np.asarray(mesh.face_normals, float)
        areas = np.asarray(mesh.area_faces, float)
        ok = np.isfinite(normals).all(1) & (areas > 0)
        normals, areas = normals[ok], areas[ok]
        total = float(areas.sum()) or 1.0
        cdirs, carea, members = normal_clusters(normals, areas)
        sin_tol = np.sin(np.radians(perp_tol_deg))

        # Directions covered elsewhere: X/Y/Z and normals of large planar caps.
        covered = [np.eye(3)[i] for i in range(3)] + [cdirs[k] for k in range(len(cdirs))
                                                     if carea[k] / total > cap_frac]
        covered = np.array(covered)
        cos_ex = np.cos(np.radians(exclude_deg))

        top = np.argsort(-carea)[:top_pairs]
        cands = []
        for a in range(len(top)):
            for b in range(a + 1, len(top)):
                c = np.cross(cdirs[top[a]], cdirs[top[b]])
                if np.linalg.norm(c) > np.sin(np.radians(10)):
                    cands.append(_canon(c))
        if not cands:
            return []
        cands = np.array(cands)
        perp = np.abs(cdirs @ cands.T) < sin_tol           # (clusters, cands)
        support = (carea[:, None] * perp).sum(0) / total
        walls = perp.sum(0)

        cos_nms = np.cos(np.radians(nms_deg))
        out = []
        for j in np.argsort(-support):
            if support[j] < min_frac or len(out) >= max_dirs:
                break
            if walls[j] < min_walls:
                continue
            inl = np.abs(normals @ cands[j]) < np.sin(np.radians(3 * perp_tol_deg))
            N, w = normals[inl], areas[inl]
            _, vecs = np.linalg.eigh((N * w[:, None]).T @ N)
            d = _canon(vecs[:, 0])
            if np.max(np.abs(covered @ d)) > cos_ex:
                continue
            if any(abs(d @ np.array(o['direction'])) > cos_nms for o in out):
                continue
            perp_d = np.abs(cdirs @ d) < sin_tol
            # A single dominant plane supports its whole great circle; require
            # real support from the other walls too.
            if (carea[perp_d].sum() - carea[perp_d].max(initial=0)) / total < min_frac:
                continue
            out.append({'direction': [round(float(x), 7) for x in d],
                        'support': round(float(carea[perp_d].sum() / total), 4),
                        'walls': int(perp_d.sum())})
    return sorted(out, key=lambda o: -o['support'])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input')
    ap.add_argument('--max-dirs', type=int, default=6)
    ap.add_argument('--min-frac', type=float, default=0.08)
    ap.add_argument('--out', default='directions.json')
    args = ap.parse_args()
    mesh = trimesh.load(args.input, force='mesh')
    res = detect_directions(mesh, max_dirs=args.max_dirs, min_frac=args.min_frac)
    json.dump(res, open(args.out, 'w'), indent=1)
    for r in res:
        print(f"direction {r['direction']} support={r['support']:.3f} walls={r['walls']}")
    print(f'wrote {len(res)} directions to {args.out}')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Whole-part section-extrusion candidates.

For each axis, the target is sectioned at the midpoint of its bounding box and
every section polygon (with holes) is extruded through the target's full
extent along that axis. Three candidates, one per axis, emitted as 'generic'
ops (self-contained CadQuery defining `solid_gen_{N}`) that greedy_search.py
adds to its candidate pool when CADFIT_SECTION_EXTRUDE=1.

Why: on the agent eval parts, this fixed three-proposal recipe beat both the
pipeline and the LLM agent (00182325: pipeline 0.52, agent 0.92, best section
extrusion 0.996); the pipeline's own extrusions had the wrong extent there.

Usage:
  python section_extrude.py mesh.stl --out section_extrude_candidates.json [--normalize]
"""
import argparse
import json
import sys

import numpy as np
import trimesh

from iou import normalize_mesh

SIMPLIFY = 0.002   # polygon simplification tolerance, normalized frame
MIN_AREA = 1e-4    # drop section slivers


def _fmt(pts):
    return '[' + ', '.join(f'({x:.5f}, {y:.5f}, {z:.5f})' for x, y, z in pts) + ']'


def _drop_axis(k):
    keep = [i for i in range(3) if i != k]
    T = np.zeros((4, 4))
    T[0, keep[0]] = 1
    T[1, keep[1]] = 1
    T[2, k] = 1
    T[3, 3] = 1
    return T


def section_polygons(mesh, k, value):
    """Section polygons (shapely, with holes) of `mesh` in the plane axis k = value,
    in the coordinates of the other two axes."""
    normal = np.eye(3)[k]
    s = mesh.section(plane_origin=normal * value, plane_normal=normal)
    if s is None:
        return []
    try:
        polys = s.to_planar(to_2D=_drop_axis(k))[0].polygons_full
    except Exception:
        return []
    out = []
    for p in polys:
        p = p.simplify(SIMPLIFY)
        if p.is_valid and p.area > MIN_AREA:
            out.append(p)
    return out


def _lift(pts2, k, value):
    """2D points in the other two axes -> 3D points on the plane axis k = value."""
    keep = [i for i in range(3) if i != k]
    P = np.zeros((len(pts2), 3))
    P[:, keep[0]], P[:, keep[1]] = pts2[:, 0], pts2[:, 1]
    P[:, k] = value
    return P


def extrusion_code(polys, k, lo, hi):
    """CadQuery code extruding each polygon (and its holes) from axis=lo to axis=hi."""
    lines = ['g{N}_solids = []']
    for p in polys:
        outer = _lift(np.asarray(p.exterior.coords)[:-1], k, lo)
        holes = [_lift(np.asarray(h.coords)[:-1], k, lo) for h in p.interiors]
        lines.append(f'g{{N}}_outer = cq.Wire.makePolygon([cq.Vector(*q) for q in {_fmt(outer)}], close=True)')
        lines.append('g{N}_holes = [' + ', '.join(
            f'cq.Wire.makePolygon([cq.Vector(*q) for q in {_fmt(h)}], close=True)' for h in holes) + ']')
        d = [0.0, 0.0, 0.0]
        d[k] = float(hi - lo)
        lines.append('g{N}_solids.append(cq.Solid.extrudeLinear(cq.Face.makeFromWires(g{N}_outer, g{N}_holes), '
                     f'cq.Vector({d[0]:.5f}, {d[1]:.5f}, {d[2]:.5f})))')
    lines += ['g{N}_shape = g{N}_solids[0] if len(g{N}_solids) == 1 else cq.Compound.makeCompound(g{N}_solids)',
              'assert g{N}_shape.isValid(), "invalid section extrusion"',
              'solid_gen_{N} = cq.Workplane("XY").add(g{N}_shape)']
    return '\n'.join(lines)


def propose(mesh):
    lo, hi = mesh.bounds
    cands = []
    for k, axis in enumerate('xyz'):
        polys = section_polygons(mesh, k, 0.5 * (lo[k] + hi[k]))
        if polys:
            cands.append({'kind': f'section_{axis}', 'code': extrusion_code(polys, k, lo[k], hi[k])})
    return cands


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mesh')
    ap.add_argument('--out', default='section_extrude_candidates.json')
    ap.add_argument('--normalize', action='store_true')
    args = ap.parse_args()
    mesh = trimesh.load(args.mesh, force='mesh')
    if args.normalize:
        mesh = normalize_mesh(mesh)
    cands = propose(mesh)
    json.dump(cands, open(args.out, 'w'), indent=1)
    print(f'wrote {len(cands)} section-extrusion candidates to {args.out}', file=sys.stderr)


if __name__ == '__main__':
    main()

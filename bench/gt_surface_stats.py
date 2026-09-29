#!/usr/bin/env python3
"""
Classify the B-rep faces of ground-truth STEP files by surface type.

For each STEP: face count and area fraction per surface type (plane, cylinder,
cone, sphere, torus, bspline, bezier, revolution, extrusion, offset, other),
plus tags for what a reconstruction would need:
  freeform  - bspline/bezier/offset area   (loft / sweep territory)
  swept     - surface of extrusion/revolution present
  tilted    - planar area whose normal is not within 2 deg of a principal axis
  toroidal  - torus area (fillets along curves, pipe bends)
  conical   - cone area (chamfers on round edges, tapers, countersinks)

Usage:
  python bench/gt_surface_stats.py bench/cadbench/dev [--out stats.json]
"""
import argparse
import glob
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp
from OCP.GeomAbs import GeomAbs_SurfaceType as ST
from OCP.GProp import GProp_GProps
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

NAMES = {
    ST.GeomAbs_Plane: 'plane', ST.GeomAbs_Cylinder: 'cylinder', ST.GeomAbs_Cone: 'cone',
    ST.GeomAbs_Sphere: 'sphere', ST.GeomAbs_Torus: 'torus', ST.GeomAbs_BSplineSurface: 'bspline',
    ST.GeomAbs_BezierSurface: 'bezier', ST.GeomAbs_SurfaceOfRevolution: 'revolution',
    ST.GeomAbs_SurfaceOfExtrusion: 'extrusion', ST.GeomAbs_OffsetSurface: 'offset',
}
AXES = np.eye(3)


def read_step(path):
    r = STEPControl_Reader()
    if r.ReadFile(path) != 1:  # IFSelect_RetDone
        return None
    r.TransferRoots()
    return r.OneShape()


def face_stats(shape):
    count, area = Counter(), defaultdict(float)
    tilted_area = 0.0
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        f = TopoDS.Face_s(exp.Current())
        exp.Next()
        s = BRepAdaptor_Surface(f)
        name = NAMES.get(s.GetType(), 'other')
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, props)
        a = props.Mass()
        count[name] += 1
        area[name] += a
        if name == 'plane':
            d = s.Plane().Axis().Direction()
            n = np.array([d.X(), d.Y(), d.Z()])
            if np.max(np.abs(AXES @ n)) < np.cos(np.radians(2)):
                tilted_area += a
    return count, area, tilted_area


def classify(path):
    shape = read_step(path)
    if shape is None:
        return {'error': 'read failed'}
    count, area, tilted = face_stats(shape)
    total = sum(area.values()) or 1.0
    frac = {k: v / total for k, v in area.items()}
    tags = []
    if frac.get('bspline', 0) + frac.get('bezier', 0) + frac.get('offset', 0) > 0.02:
        tags.append('freeform')
    if frac.get('revolution', 0) + frac.get('extrusion', 0) > 0.02:
        tags.append('swept')
    if tilted / total > 0.02:
        tags.append('tilted')
    if frac.get('torus', 0) > 0.02:
        tags.append('toroidal')
    if frac.get('cone', 0) > 0.02:
        tags.append('conical')
    return {'faces': sum(count.values()), 'count': dict(count),
            'area_frac': {k: round(v, 4) for k, v in sorted(frac.items())},
            'tilted_frac': round(tilted / total, 4), 'tags': tags}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('folders', nargs='+')
    ap.add_argument('--out')
    args = ap.parse_args()
    out = {}
    for folder in args.folders:
        for p in sorted(glob.glob(os.path.join(folder, '*.step'))):
            key = os.path.splitext(os.path.basename(p))[0]
            out[key] = classify(p)
            r = out[key]
            print(f"{key:<48} faces={r.get('faces')} tags={','.join(r.get('tags', [])) or '-'}", file=sys.stderr)
    tag_n = Counter(t for r in out.values() for t in r.get('tags', []))
    agg = defaultdict(float)
    for r in out.values():
        for k, v in r.get('area_frac', {}).items():
            agg[k] += v / max(len(out), 1)
    print(f'\n{len(out)} shapes; tag counts: {dict(tag_n)}', file=sys.stderr)
    print('mean area fraction: ' + ', '.join(f'{k}={v:.3f}' for k, v in sorted(agg.items(), key=lambda x: -x[1])),
          file=sys.stderr)
    if args.out:
        json.dump(out, open(args.out, 'w'), indent=1)


if __name__ == '__main__':
    main()

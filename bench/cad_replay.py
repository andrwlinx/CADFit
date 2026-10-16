#!/usr/bin/env python3
"""
Replay a reconstruction's CadQuery program and check the CAD it builds.

Under --exact-union the scored STL is a manifold3d union of cached candidate
meshes, so a good mesh score does not show that the emitted program builds a
valid solid (p3test2_beam 00706786 scored 0.980 while its CAD fails
isValid()). This runs the program in a fresh process, takes `final_result`
(or `result`), checks OCC validity of the shape and of each solid, and
tessellates it to an STL that bench/score.py judges like any reconstruction.

Usage: python bench/cad_replay.py <program.py> <out.stl>   # prints one JSON line
"""
import json
import sys
import time


def main():
    prog, out_stl = sys.argv[1], sys.argv[2]
    t0 = time.time()
    rec = {'built': False, 'valid': False, 'n_solids': 0, 'n_invalid_solids': None}
    try:
        import cadquery as cq
        ns = {}
        exec(compile(open(prog).read(), prog, 'exec'), ns)
        res = ns.get('final_result', ns.get('result'))
        if res is None:
            raise RuntimeError('program defines neither final_result nor result')
        shape = res.val() if isinstance(res, cq.Workplane) else res
        if isinstance(res, cq.Workplane) and len(res.vals()) > 1:
            shape = cq.Compound.makeCompound([v for v in res.vals() if isinstance(v, cq.Shape)])
        solids = shape.Solids()
        rec['n_solids'] = len(solids)
        rec['n_invalid_solids'] = sum(not s.isValid() for s in solids)
        rec['valid'] = bool(shape.isValid() and solids and rec['n_invalid_solids'] == 0)
        cq.exporters.export(shape, out_stl, tolerance=1e-3, angularTolerance=0.1)
        rec['built'] = True
    except Exception as e:  # noqa: BLE001 - any failure means the program does not build
        rec['error'] = f'{type(e).__name__}: {str(e)[:300]}'
    rec['seconds'] = round(time.time() - t0, 1)
    print(json.dumps(rec))


if __name__ == '__main__':
    main()

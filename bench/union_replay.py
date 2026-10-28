#!/usr/bin/env python3
"""
Replay a CAD program and tessellate the boundary of the volume it occupies.

A delivered program may build a compound of overlapping or touching solids; the
judge scores their union, but the compound's tessellation carries the faces
buried between them (and an STL roundtrip can merge the solids into one
connected body, so a mesh-level body count cannot tell). For surface agreement
(bench/detail_scores.py) the solids are fused with the OCC boolean (plain, then
fuzzy 1e-5 and 1e-4, as exec_verify's _fuse) and the fused shape is tessellated
with bench/cad_replay.py's tolerances. A single solid is tessellated as is.

Usage: python bench/union_replay.py <program.py> <out.stl> [scale]   # prints one JSON line
(scale: applied before tessellating, e.g. 0.01 for CADFather's frame.)
"""
import json
import sys
import time


def main():
    prog, out_stl = sys.argv[1], sys.argv[2]
    scale = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
    t0 = time.time()
    rec = {'built': False, 'fused': False, 'n_solids': 0}
    try:
        import cadquery as cq
        ns = {'__name__': '__main__'}
        src = '\n'.join(l for l in open(prog).read().splitlines() if 'exporters.export' not in l)
        exec(compile(src, prog, 'exec'), ns)
        res = ns.get('final_result', ns.get('result', ns.get('r')))
        shape = res.val() if isinstance(res, cq.Workplane) else res
        if isinstance(res, cq.Workplane) and len(res.vals()) > 1:
            shape = cq.Compound.makeCompound([v for v in res.vals() if isinstance(v, cq.Shape)])
        if scale != 1.0:
            shape = shape.scale(scale)
        solids = shape.Solids()
        rec['n_solids'] = len(solids)
        out = solids[0] if len(solids) == 1 else None
        if len(solids) > 1:
            for tol in (None, 1e-5, 1e-4):
                try:
                    u = solids[0].fuse(*solids[1:], tol=tol).clean()
                    if u.isValid() and u.Volume() > 0:
                        out, rec['fuse_tol'] = u, tol
                        break
                except Exception:  # noqa: BLE001
                    continue
        if out is None:
            raise RuntimeError('fuse failed')
        rec['fused'] = len(solids) > 1
        cq.exporters.export(out, out_stl, tolerance=1e-3, angularTolerance=0.1)
        rec['built'] = True
    except Exception as e:  # noqa: BLE001
        rec['error'] = f'{type(e).__name__}: {str(e)[:300]}'
    rec['seconds'] = round(time.time() - t0, 1)
    print(json.dumps(rec))


if __name__ == '__main__':
    main()

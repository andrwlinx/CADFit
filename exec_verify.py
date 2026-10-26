#!/usr/bin/env python3
"""
Execution-verified program assembly (CADFit++ --exec-verify).

The pipeline scores every model during search on meshes (manifold3d unions of
cached candidate STLs), and the program it writes composes the solids with
`.add()`: a Compound of overlapping solids, not one solid. Cuts on such a
compound are where OCC booleans fail (`Null TopoDS_Shape` in fresh_beamkh
00642725 / 00883892 / 00983172), and a compound of 100+ overlapping solids is
often not isValid() (local repro of fresh_beamsec 00090768: 133 solids, one
invalid). So the mesh score is not the score of the program.

This stage runs after search, on the final program:
  1. `fused` variant: every solid-level `.add(X)` becomes a boolean fuse and
     every `.cut(X)` a boolean cut, through two helpers embedded in the program
     (`_fuse`, `_cut`) that retry with OCC fuzzy tolerances 1e-5 and 1e-4 when
     the plain boolean throws or returns an invalid / empty shape. A fuse that
     still fails keeps both bodies as a compound; a cut that still fails is
     skipped. Either fallback is visible in the executed score below.
  2. Each variant (original, fused) is executed in a fresh process
     (bench/cad_replay.py: shape + per-solid OCC validity, tessellation) and the
     tessellation is judged against the target mesh — the method's input — with
     the robust judge (bench/score.py).
  3. Selection: the highest executed IoU among valid programs; only when no
     program is valid, the highest executed IoU among those that build (the
     record says so: `chosen_valid` False, validity-gated score 0). The chosen
     program and its executed tessellation become the final outputs, so the
     saved STL is what the program builds.

Programs whose composition can be rewritten get both variants; fallbacks
passed as `alternatives` (pre-refinement program, best single candidate) are
executed and judged the same way.

Usage: python exec_verify.py <program.py> <target.stl> <out_dir> [name=alt.py ...]   # prints JSON
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# Arm code snapshots (bench/runs/<tag>_<arm>_code) hold only the top-level
# modules; bench/ then comes from the checkout the runner starts in.
if not os.path.exists(os.path.join(HERE, 'bench', 'cad_replay.py')):
    HERE = os.getcwd()
TIMEOUT = 600

HELPERS = '''
def _shape(w):
    if isinstance(w, cq.Workplane):
        vs = [v for v in w.vals() if isinstance(v, cq.Shape)]
        return vs[0] if len(vs) == 1 else cq.Compound.makeCompound(vs)
    return w


def _good(s):
    try:
        return s is not None and s.isValid() and s.Volume() > 1e-9
    except Exception:
        return False


def _fuse(a, b):
    """Boolean union; fuzzy retries; if all fail, keep both bodies as a compound."""
    A, B = _shape(a), _shape(b)
    for tol in (None, 1e-5, 1e-4):
        try:
            r = A.fuse(B, tol=tol).clean()
            if _good(r):
                return cq.Workplane("XY").newObject([r])
        except Exception:
            pass
    return cq.Workplane("XY").newObject([cq.Compound.makeCompound([A, B])])


def _cut(a, b):
    """Boolean difference; fuzzy retries; if all fail, the cut is skipped."""
    A, B = _shape(a), _shape(b)
    for tol in (None, 1e-5, 1e-4):
        try:
            r = A.cut(B, tol=tol).clean()
            if _good(r):
                return cq.Workplane("XY").newObject([r])
        except Exception:
            pass
    return cq.Workplane("XY").newObject([A])

'''

# Solid-level composition lines as the generators write them (cadquery_ops.py
# final script, run_pipeline.combine_cadquery_scripts). Sketch-level `.add(loop)`
# lines have the form `sketch_x=sketch_x.add(loop_x)` and are not matched.
_ADD = re.compile(r'^(\s*)(result|final_result)\s*=\s*(\w+)\.add\((\w+)\)\s*$')
_CUT = re.compile(r'^(\s*)(result|final_result)\s*=\s*(\w+)\.cut\((\w+)\)\s*$')


# Repair pass (lit scan: repair before discarding): appended to a program whose
# shape builds but is OCC-invalid. Each invalid solid is replaced by its
# ShapeFix_Shape result when that is valid, else dropped; the variant is judged
# like any other, so a repair that loses geometry loses on IoU (00365747: an
# invalid solid held ~60% of the volume) and one that keeps it wins (00232213:
# valid 0.8725 vs the fused rewrite's 0.8609).
REPAIR = '''

def _repair(res):
    from OCP.ShapeFix import ShapeFix_Shape
    shape = res.val() if isinstance(res, cq.Workplane) else res
    if isinstance(res, cq.Workplane) and len(res.vals()) > 1:
        shape = cq.Compound.makeCompound([v for v in res.vals() if isinstance(v, cq.Shape)])
    keep = []
    for s in shape.Solids():
        if not s.isValid():
            f = ShapeFix_Shape(s.wrapped)
            f.Perform()
            s = cq.Shape.cast(f.Shape())
            if not s.isValid():
                continue
        keep.extend(s.Solids())
    return cq.Workplane('XY').newObject([cq.Compound.makeCompound(keep)])


result = _repair(final_result if 'final_result' in globals() else result)
final_result = result
'''


# Silhouette trim (2026-10-26): the delivered CAD often carries material outside
# the target (on the dev cohort up to ~12% of its volume), and on some parts most
# of it lies outside the target's X/Y/Z silhouettes. The target lies inside the
# prism over each of its silhouettes, so intersecting with the three prisms can
# only remove material the target does not have (up to SIL_BUFFER). Judged as one
# more variant of the best valid program: kept only if it builds, is valid and
# scores higher.
SIL_BUFFER = 0.002   # silhouettes grown by this much (normalized frame) ...
SIL_SIMPLIFY = 0.001  # ... before simplifying by less, so they still contain the target


def silhouettes(target):
    """Per axis, the target's projected outline as shapely (Multi)Polygon."""
    import numpy as np
    import trimesh
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    sys.path.insert(0, HERE)
    import iou
    m = iou.normalize_mesh(trimesh.load(target, force='mesh'))
    out = []
    for k in range(3):
        keep = [i for i in range(3) if i != k]
        tri = m.vertices[m.faces][:, :, keep]
        area = np.abs(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])) / 2
        polys = [Polygon(t) for t in tri[area > 1e-12]]
        out.append(unary_union(polys).buffer(SIL_BUFFER).simplify(SIL_SIMPLIFY))
    return out


def trim_code(sils, lo=-1.2, hi=1.2):
    """CadQuery source that intersects `result` with the prisms over `sils`."""
    def wire(coords, k):
        pts = []
        for x, y in list(coords)[:-1]:
            q = [0.0, 0.0, 0.0]
            keep = [i for i in range(3) if i != k]
            q[keep[0]], q[keep[1]], q[k] = x, y, lo
            pts.append('(%.5f, %.5f, %.5f)' % tuple(q))
        return 'cq.Wire.makePolygon([cq.Vector(*q) for q in [%s]], close=True)' % ', '.join(pts)
    lines = ['', '', '_SIL = []']
    for k, sil in enumerate(sils):
        geoms = list(getattr(sil, 'geoms', [sil]))
        d = [0.0, 0.0, 0.0]
        d[k] = hi - lo
        lines.append('_p = []')
        for g in geoms:
            holes = ', '.join(wire(h.coords, k) for h in g.interiors)
            lines.append(f'_p.append(cq.Solid.extrudeLinear(cq.Face.makeFromWires({wire(g.exterior.coords, k)}, '
                         f'[{holes}]), cq.Vector({d[0]}, {d[1]}, {d[2]})))')
        lines.append('_SIL.append(_p[0] if len(_p) == 1 else cq.Compound.makeCompound(_p))')
    lines += ['', '',
              'def _trim(res):',
              '    shape = res.val() if isinstance(res, cq.Workplane) else res',
              '    if isinstance(res, cq.Workplane) and len(res.vals()) > 1:',
              '        shape = cq.Compound.makeCompound([v for v in res.vals() if isinstance(v, cq.Shape)])',
              '    for p in _SIL:',
              '        shape = shape.intersect(p).clean()',
              '    return cq.Workplane("XY").newObject([shape])',
              '', '',
              "result = _trim(final_result if 'final_result' in globals() else result)",
              'final_result = result', '']
    return '\n'.join(lines)


def fuse_program(src):
    """Rewrite a generated program so solids are fused/cut, not compounded."""
    out, n = [], 0
    for line in src.split('\n'):
        m = _ADD.match(line) or _CUT.match(line)
        if m and 'sketch' not in m.group(3):
            fn = '_fuse' if _ADD.match(line) else '_cut'
            line = f'{m.group(1)}{m.group(2)} = {fn}({m.group(3)}, {m.group(4)})'
            n += 1
        out.append(line)
    text = '\n'.join(out)
    head = 'import cadquery as cq\n'
    i = text.find(head)
    text = (text[:i + len(head)] + HELPERS + text[i + len(head):]) if i >= 0 else head + HELPERS + text
    return text, n


def _strip_exports(src):
    return '\n'.join(ln for ln in src.split('\n')
                     if 'cq.exporters.export' not in ln and not ln.lstrip().startswith('print('))


def execute(prog, out_stl, target):
    """Fresh-process replay + robust judge against the target. Returns a record."""
    try:
        p = subprocess.run([sys.executable, os.path.join(HERE, 'bench', 'cad_replay.py'), prog, out_stl],
                           capture_output=True, text=True, timeout=TIMEOUT, cwd=os.path.dirname(prog))
        rec = json.loads(p.stdout.strip().splitlines()[-1])
    except subprocess.TimeoutExpired:
        rec = {'built': False, 'valid': False, 'error': f'timeout {TIMEOUT}s'}
    except (IndexError, json.JSONDecodeError):
        rec = {'built': False, 'valid': False, 'error': 'replay crashed'}
    rec['iou_exec'] = 0.0
    if rec.get('built') and os.path.exists(out_stl):
        sys.path.insert(0, os.path.join(HERE, 'bench'))
        import score
        try:
            j = score.robust_iou(target, out_stl)
            rec['iou_exec'] = float(j['iou'])
            rec['judge'] = {k: j[k] for k in ('method', 'se') if k in j}
        except Exception as e:  # noqa: BLE001
            rec['judge_error'] = f'{type(e).__name__}: {e}'
    return rec


def choose(recs):
    """recs: {name: record}. The best valid program; the best built one only if none is valid."""
    built = {k: r for k, r in recs.items() if r.get('built')}
    if not built:
        return None
    valid = {k: r for k, r in built.items() if r.get('valid')}
    pool = valid or built
    return max(pool, key=lambda k: pool[k]['iou_exec'])


def verify(program, target, out_dir, alternatives=(), trim=None):
    """alternatives: [(name, program_path)] fallbacks executed the same way
    (e.g. the pre-refinement search program and the best single candidate).
    trim: also judge the best valid program cut to the target's silhouettes
    (default: CADFIT_SIL_TRIM=1)."""
    if trim is None:
        trim = os.environ.get('CADFIT_SIL_TRIM') == '1'
    os.makedirs(out_dir, exist_ok=True)
    src = _strip_exports(open(program).read())
    fused, n_ops = fuse_program(src)
    variants = {'original': src, 'fused': fused}
    for name, path in alternatives:
        if path and os.path.exists(path) and os.path.abspath(path) != os.path.abspath(program):
            alt = _strip_exports(open(path).read())
            variants[name] = alt
            alt_fused, k = fuse_program(alt)
            if k:
                variants[name + '_fused'] = alt_fused
    # Identical programs (e.g. no refinement step: final == search) run once.
    uniq, alias = {}, {}
    for name, code in variants.items():
        same = [k for k, c in uniq.items() if c == code]
        if same:
            alias[name] = same[0]
        else:
            uniq[name] = code
    jobs = {}
    for name, code in uniq.items():
        py = os.path.join(out_dir, f'exec_{name}.py')
        open(py, 'w').write(code)
        jobs[name] = (py, os.path.join(out_dir, f'exec_{name}.stl'), target)
    from concurrent.futures import ProcessPoolExecutor
    # Up to ~10 variants; each replay + judge can take a few GB on a big target.
    with ProcessPoolExecutor(max_workers=min(len(jobs), 6)) as ex:
        futs = {k: ex.submit(execute, *v) for k, v in jobs.items()}
        recs = {k: f.result() for k, f in futs.items()}
        # Second pass: a repaired copy of every program that builds an invalid shape.
        rep = {}
        for name in [k for k, r in recs.items() if r.get('built') and not r.get('valid')]:
            py = os.path.join(out_dir, f'exec_{name}_repair.py')
            open(py, 'w').write(uniq[name] + REPAIR)
            rep[name + '_repair'] = ex.submit(execute, py, os.path.join(out_dir, f'exec_{name}_repair.stl'), target)
        recs.update({k: f.result() for k, f in rep.items()})
        srcs = dict(uniq)
        srcs.update({k + '_repair': uniq[k] + REPAIR for k in uniq if k + '_repair' in recs})
        # Third pass: the best valid program, trimmed to the target's silhouettes.
        valid = [k for k, r in recs.items() if r.get('valid')]
        if trim and valid:
            best = max(valid, key=lambda k: recs[k]['iou_exec'])
            try:
                code = srcs[best] + trim_code(silhouettes(target))
                py = os.path.join(out_dir, f'exec_{best}_trim.py')
                open(py, 'w').write(code)
                recs[best + '_trim'] = ex.submit(execute, py, os.path.join(out_dir, f'exec_{best}_trim.stl'),
                                                 target).result()
            except Exception as e:  # noqa: BLE001
                recs[best + '_trim'] = {'built': False, 'valid': False, 'iou_exec': 0.0,
                                        'error': f'trim not built: {type(e).__name__}: {e}'}
    pick = choose(recs)
    for name, same in alias.items():
        recs[name] = {'same_program_as': same}
    ok = bool(pick) and bool(recs[pick].get('valid'))
    return {'chosen': pick, 'chosen_valid': ok, 'n_rewritten_ops': n_ops, 'variants': recs,
            'validity_gated_iou': recs[pick]['iou_exec'] if ok else 0.0,
            'program': os.path.join(out_dir, f'exec_{pick}.py') if pick else None,
            'stl': os.path.join(out_dir, f'exec_{pick}.stl') if pick else None}


if __name__ == '__main__':
    alts = [(a.split('=', 1)[0], os.path.abspath(a.split('=', 1)[1])) for a in sys.argv[4:]]
    print(json.dumps(verify(os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]),
                            os.path.abspath(sys.argv[3]), alts), indent=1))

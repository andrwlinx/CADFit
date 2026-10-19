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
  3. Selection: the highest executed IoU among valid programs, unless an
     invalid program beats it by more than VALID_MARGIN (then the highest
     executed IoU overall). The chosen program and its executed tessellation
     become the final outputs, so the saved STL is what the program builds.

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
VALID_MARGIN = 0.005   # an invalid program must beat the best valid one by this much
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
            rec['iou_exec'] = float(score.robust_iou(target, out_stl)['iou'])
        except Exception as e:  # noqa: BLE001
            rec['judge_error'] = f'{type(e).__name__}: {e}'
    return rec


def choose(recs):
    """recs: {name: record}. Best valid unless an invalid one wins by VALID_MARGIN."""
    built = {k: r for k, r in recs.items() if r.get('built')}
    if not built:
        return None
    best = max(built, key=lambda k: built[k]['iou_exec'])
    valid = {k: r for k, r in built.items() if r.get('valid')}
    if valid:
        bv = max(valid, key=lambda k: valid[k]['iou_exec'])
        if built[best]['iou_exec'] <= valid[bv]['iou_exec'] + VALID_MARGIN:
            return bv
    return best


def verify(program, target, out_dir, alternatives=()):
    """alternatives: [(name, program_path)] fallbacks executed the same way
    (e.g. the pre-refinement search program and the best single candidate)."""
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
    with ProcessPoolExecutor(max_workers=len(jobs)) as ex:
        futs = {k: ex.submit(execute, *v) for k, v in jobs.items()}
        recs = {k: f.result() for k, f in futs.items()}
    pick = choose(recs)
    for name, same in alias.items():
        recs[name] = {'same_program_as': same}
    return {'chosen': pick, 'n_rewritten_ops': n_ops, 'variants': recs,
            'program': os.path.join(out_dir, f'exec_{pick}.py') if pick else None,
            'stl': os.path.join(out_dir, f'exec_{pick}.stl') if pick else None}


if __name__ == '__main__':
    alts = [(a.split('=', 1)[0], os.path.abspath(a.split('=', 1)[1])) for a in sys.argv[4:]]
    print(json.dumps(verify(os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]),
                            os.path.abspath(sys.argv[3]), alts), indent=1))

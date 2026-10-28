#!/usr/bin/env python3
"""
CADFather outputs (agent/run_folder.sh --out <dir>: <part>.py per part) as a
CADFit run folder that bench/score.py --cad judges like any arm.

Runs in CADFather's own environment (its programs import its `cadgen`
library), e.g. inside its sandbox from the CADFather repo root:

  python /path/to/cadfit/bench/cadfather_adapt.py <cadfather_out> <cadfit>/bench/runs/<tag>

For each part the program is executed, the shape is checked exactly as
bench/cad_replay.py checks ours (OCC isValid of the shape and of every solid),
scaled from CADFather's frame into ours, and tessellated with the same
tolerances. Frames: both centre the target's bounding box at the origin;
CADFather scales its largest extent to 200 (agent/cad_agent/capabilities/
metrics.py normalize_mesh: GT to a unit cube, prediction / 200), ours to 2
(iou.normalize_mesh), so ours = CADFather's / 100.

Written per part: best_greedy_parallel.py (the program, for reference; it does
not run in CADFit's environment), best_greedy_parallel.stl and
best_greedy_parallel_cad.stl (the scaled tessellation), best_greedy_parallel_cad.json
(the replay record score.py's cad_replay cache reads), best_greedy_parallel_union.stl
+ .json (the fused solids for bench/detail_scores.py; union_replay.py must sit next
to this script). A part with no program
gets no folder entry beyond an empty directory, which score.py counts as 0.
"""
import json
import os
import shutil
import sys
import time

SCALE = 0.01


def replay(prog, out_stl):
    rec = {'built': False, 'valid': False, 'n_solids': 0, 'n_invalid_solids': None,
           'source': 'cadfather', 'scale': SCALE}
    t0 = time.time()
    try:
        import cadquery as cq
        ns = {'__name__': '__main__'}
        exec(compile(open(prog).read(), prog, 'exec'), ns)
        res = ns.get('r', ns.get('result'))
        if res is None:
            raise RuntimeError('program defines neither r nor result')
        shape = res.val() if isinstance(res, cq.Workplane) else res
        if isinstance(res, cq.Workplane) and len(res.vals()) > 1:
            shape = cq.Compound.makeCompound([v for v in res.vals() if isinstance(v, cq.Shape)])
        shape = shape.scale(SCALE)
        solids = shape.Solids()
        rec['n_solids'] = len(solids)
        rec['n_invalid_solids'] = sum(not s.isValid() for s in solids)
        rec['valid'] = bool(shape.isValid() and solids and rec['n_invalid_solids'] == 0)
        cq.exporters.export(shape, out_stl, tolerance=1e-3, angularTolerance=0.1)
        rec['built'] = True
    except Exception as e:  # noqa: BLE001
        rec['error'] = f'{type(e).__name__}: {str(e)[:300]}'
    rec['seconds'] = round(time.time() - t0, 1)
    return rec


def main(cf_out, run_dir):
    os.makedirs(run_dir, exist_ok=True)
    for f in sorted(os.listdir(cf_out)):
        if not f.endswith('.py') or f.startswith('config'):
            continue
        part = f[:-3]
        d = os.path.join(run_dir, part)
        os.makedirs(d, exist_ok=True)
        prog = os.path.join(d, 'best_greedy_parallel.py')
        shutil.copy2(os.path.join(cf_out, f), prog)
        cad_stl = os.path.join(d, 'best_greedy_parallel_cad.stl')
        rec = replay(prog, cad_stl)
        if rec['built']:
            shutil.copy2(cad_stl, os.path.join(d, 'best_greedy_parallel.stl'))
        json.dump(rec, open(os.path.join(d, 'best_greedy_parallel_cad.json'), 'w'))
        # The fused boundary detail_scores.py reads (the program runs only in this env).
        if rec['built']:
            import subprocess
            p = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'union_replay.py'), prog, os.path.join(d, 'best_greedy_parallel_union.stl'),
                                str(SCALE)], capture_output=True, text=True)
            try:
                urec = json.loads(p.stdout.strip().splitlines()[-1])
            except (IndexError, json.JSONDecodeError):
                urec = {'built': False, 'error': p.stderr[-300:]}
            json.dump(urec, open(os.path.join(d, 'best_greedy_parallel_union.json'), 'w'))
        print(part[:8], json.dumps(rec), flush=True)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])

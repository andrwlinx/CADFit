#!/usr/bin/env python3
"""
Function-level profile (cProfile) of extract_sketch + fit_extrude + fit_revolve on one development
part, for the code given by --modules (prepended to sys.path; e.g. the f4435df versions of
fit_primitives.py and analyze_revolve_axis.py) -> a text report (top functions by cumulative time).

  .venv/bin/python bench/profile_functions.py --modules OLD --part <dev stl> --out results/tools/cprofile_original.txt
"""
import argparse
import cProfile
import io
import os
import pstats
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--modules', default=None)
    ap.add_argument('--part', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    assert 'fresh2' not in a.part and 'fresh3' not in a.part
    os.environ['CADFIT_AGENT_EXEC'] = '1'
    sys.path[:0] = [os.path.join(ROOT, 'agent'), os.path.join(ROOT, 'bench'), ROOT]
    if a.modules:  # register the given module versions before anything imports the repo's copies
        import importlib.util
        for name in ('fit_primitives', 'analyze_revolve_axis'):
            spec = importlib.util.spec_from_file_location(name, os.path.join(a.modules, name + '.py'))
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
    import skills
    import fit_primitives
    ws = skills.SkillWorkspace(a.part, tempfile.mkdtemp())
    pr = cProfile.Profile()
    pr.enable()
    r = ws.extract_sketch(normal=[0, 0, 1], offset=0.0)
    sid = r['sketches'][0]['id']
    ws.fit_extrude(sketch=sid)
    ws.fit_revolve(sketch=sid)
    pr.disable()
    buf = io.StringIO()
    pstats.Stats(pr, stream=buf).sort_stats('cumulative').print_stats(30)
    head = f'part: {os.path.relpath(a.part, ROOT)}\nfit_primitives: {fit_primitives.__file__}\n\n'
    open(a.out, 'w').write(head + buf.getvalue())
    print(head + buf.getvalue()[:3000])


if __name__ == '__main__':
    main()

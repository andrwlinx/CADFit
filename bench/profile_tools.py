#!/usr/bin/env python3
"""
Where agent tool time goes, stage by stage, on development parts (never the reserved
fresh2 parts): runs the no-LLM skills policy (agent/scripted_skills_policy.py) under
tools v2 (CADFIT_AGENT_EXEC=1) with timers around each stage a tool call spends time in.

Stages: slice (skills._es.slice_mesh_loops), nest (_nest), fit (profile fitting,
_fp.build_action_instances_from_entry), translation (fit_extrude's extent sweep,
_alt.process_single_sketch), run_code (one step's program in the sandbox),
boolean (manifold IoU of the step model, CadWorkspace._score), replay (the assembled
program in the sandbox, cad_replay.py), judge (score.robust_iou), manifold
(iou._cached_manifold of the executed STL), other (the rest of the call).

  .venv/bin/python bench/profile_tools.py --n 6 --max-minutes 10 --out results/tools/profile_v2.json
"""
import argparse
import collections
import json
import os
import sys
import tempfile
import time

os.environ.setdefault('CADFIT_AGENT_EXEC', '1')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'agent'), os.path.join(ROOT, 'bench'), ROOT]

import cad_tools  # noqa: E402
import iou  # noqa: E402
import score  # noqa: E402
import scripted_skills_policy as policy  # noqa: E402
import skills  # noqa: E402

STAGE = collections.defaultdict(float)  # stage seconds inside the current tool call
CALLS = []                               # one record per tool call
_depth = [0]


def timed(stage, fn):
    def w(*a, **k):
        t = time.time()
        try:
            return fn(*a, **k)
        finally:
            STAGE[stage] += time.time() - t
    return w


def timed_replay(fn):
    """subprocess.run inside cad_tools: the replay of the assembled program vs one step's code."""
    def w(argv, *a, **k):
        stage = 'replay' if any('cad_replay.py' in str(x) for x in argv) else 'run_code'
        return timed(stage, fn)(argv, *a, **k)
    return w


def tool(name, fn):
    def w(*a, **k):
        if _depth[0]:
            return fn(*a, **k)
        _depth[0] += 1
        STAGE.clear()
        t = time.time()
        try:
            return fn(*a, **k)
        finally:
            _depth[0] -= 1
            total = time.time() - t
            rec = {'tool': name, 'seconds': round(total, 2), **{s: round(v, 2) for s, v in STAGE.items()}}
            rec['other'] = round(total - sum(STAGE.values()), 2)
            CALLS.append(rec)
    return w


def install():
    skills._es.slice_mesh_loops = timed('slice', skills._es.slice_mesh_loops)
    skills._nest = timed('nest', skills._nest)
    skills._fp.build_action_instances_from_entry = timed('fit', skills._fp.build_action_instances_from_entry)
    skills._alt.process_single_sketch = timed('translation', skills._alt.process_single_sketch)
    cad_tools.subprocess.run = timed_replay(cad_tools.subprocess.run)
    score.robust_iou = timed('judge', score.robust_iou)
    iou._cached_manifold = timed('manifold', iou._cached_manifold)
    cad_tools.CadWorkspace._score = timed('boolean', cad_tools.CadWorkspace._score)
    for name in ('describe_target', 'detect_directions', 'section_extrude', 'extract_sketch', 'fit_extrude',
                 'fit_revolve', 'add_candidate', 'add_code', 'remove_step', 'evaluate', 'section'):
        for cls in (skills.SkillWorkspace, cad_tools.CadWorkspace):  # where the method is defined
            if name in cls.__dict__:
                setattr(cls, name, tool(name, cls.__dict__[name]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stl-dir', default=os.path.join(ROOT, 'bench', 'cadbench', 'fresh'))
    ap.add_argument('--n', type=int, default=6, help='development parts, the first n of the 20-part study sample')
    ap.add_argument('--max-minutes', type=float, default=10)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    if 'fresh2' in os.path.abspath(a.stl_dir):
        sys.exit('profile on development parts only, not fresh2')
    install()
    parts = policy.study_parts(a.stl_dir)[:a.n]
    out = {'parts': {}, 'stl_dir': a.stl_dir}
    for p in parts:
        CALLS.clear()
        t = time.time()
        policy.run_part(os.path.join(a.stl_dir, p + '.stl'), tempfile.mkdtemp(prefix='prof_'), max_minutes=a.max_minutes)
        out['parts'][p] = {'seconds': round(time.time() - t, 1), 'calls': list(CALLS)}
        tot = collections.Counter()
        for c in CALLS:
            for k, v in c.items():
                if k not in ('tool', 'seconds'):
                    tot[k] += v
        print(f'{p[:8]} {time.time() - t:6.0f}s  ' + '  '.join(f'{k} {v:.0f}' for k, v in tot.most_common()), flush=True)
    stages, by_tool = collections.Counter(), collections.defaultdict(lambda: [0, 0.0])
    for r in out['parts'].values():
        for c in r['calls']:
            by_tool[c['tool']][0] += 1
            by_tool[c['tool']][1] += c['seconds']
            for k, v in c.items():
                if k not in ('tool', 'seconds'):
                    stages[k] += v
    total = sum(stages.values())
    out['stages'] = {k: round(v, 1) for k, v in stages.most_common()}
    out['tools'] = {k: {'n': v[0], 'seconds': round(v[1], 1)} for k, v in by_tool.items()}
    print('\nstage share: ' + '  '.join(f'{k} {100 * v / total:.0f}%' for k, v in stages.most_common()))
    for k, v in sorted(by_tool.items(), key=lambda x: -x[1][1]):
        print(f'{k:18s} n={v[0]:4d} total {v[1]:7.0f}s mean {v[1] / v[0]:6.1f}s')
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, 'w'), indent=1)


if __name__ == '__main__':
    main()

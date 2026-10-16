#!/usr/bin/env python3
"""
No-LLM control for the skills toolset: a fixed policy that calls the same
skills an agent gets, under the same budget, then assembles greedily.

  1. describe_target, detect_directions
  2. extract_sketch at the middle of the target along each axis, each flat-face
     normal and each detected direction; fit_extrude every sketch, and
     fit_revolve the axis sketches
  3. section_extrude along x, y, z
  4. greedy assembly: start from the best candidate, then repeatedly add (union
     or cut) the candidate that raises IoU most, until nothing gains 0.001

Every skill call and every add/cut counts against --max-calls, and the clock
against --max-minutes, as tool calls and wall time do for an agent episode.

  .venv/bin/python agent/scripted_skills_policy.py --parts P1 P2 --out bench/runs/agentsk_policy
  .venv/bin/python agent/scripted_skills_policy.py --smoke     # 3 study parts -> /tmp/agentsk_policy
"""
import argparse
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from skills import SkillWorkspace  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRESH = os.path.join(ROOT, 'bench', 'cadbench', 'fresh')


def study_parts(stl_dir=FRESH, n=20, seed=1):
    """The agent-skills study sample (ledger A-005): n parts, fixed before any outcome."""
    names = sorted(f[:-4] for f in os.listdir(stl_dir) if f.endswith('.stl'))
    return sorted(random.Random(seed).sample(names, min(n, len(names))))


class Budget(Exception):
    pass


def run_part(gt, out, max_calls=40, max_minutes=30.0, min_gain=1e-3):
    t0 = time.time()
    ws = SkillWorkspace(gt, os.path.join(out, 'work'))
    calls = []

    def call(name, **args):
        if len(calls) >= max_calls or time.time() - t0 > 60 * max_minutes:
            raise Budget()
        res = getattr(ws, name)(**args)
        calls.append({'name': name, 'args': args, 't': round(time.time() - t0, 1),
                      'error': res.get('error') if isinstance(res, dict) else None})
        return res

    stop = 'done'
    try:
        info = call('describe_target')
        dirs = call('detect_directions')
        normals = [tuple(a) for a in dirs['axes']]
        for f in dirs['flat_face_normals'] + [{'normal': d['direction']} for d in dirs['other_directions']]:
            if all(abs(sum(p * q for p, q in zip(f['normal'], m))) < 0.999 for m in normals):
                normals.append(tuple(f['normal']))
        verts = ws.gt_mesh.vertices
        for k, nrm in enumerate(normals):
            proj = (verts * nrm).sum(1)
            mid = 0.5 * (proj.min() + proj.max())
            for s in call('extract_sketch', normal=list(nrm), offset=float(mid))['sketches']:
                call('fit_extrude', sketch=s['id'])
                if k < 3:
                    call('fit_revolve', sketch=s['id'])
        for axis in 'xyz':
            call('section_extrude', axis=axis)
        # Greedy assembly over the candidates the skills made.
        cands = sorted(ws.candidates, key=lambda c: -ws.candidates[c]['iou'])
        if cands:
            call('add_candidate', id=cands[0])
            while True:
                base = ws._score(ws._model())
                best = (min_gain, None, None)
                for c in cands:
                    m = ws.candidates[c]['_m']
                    for mode in ('add', 'cut'):
                        cur = ws._model()
                        s = ws._score(cur + m if mode == 'add' else cur - m)
                        if s - base > best[0]:
                            best = (s - base, c, mode)
                if best[1] is None:
                    break
                call('add_candidate', id=best[1], mode=best[2])
    except Budget:
        stop = 'budget'
    stl = ws.export(out)
    result = {'model': 'scripted-skills-policy', 'toolset': 'skills', 'gt': gt, 'init': None, 'init_iou': 0.0,
              'best_iou': ws.best[0], 'n_steps': len(ws.best[1]),
              'sources': [s['source'] for s in ws.best[1]], 'modes': [s['mode'] for s in ws.best[1]],
              'tool_calls': len(calls), 'stop': stop, 'seconds': round(time.time() - t0, 1),
              'n_candidates': len(ws.candidates), 'n_sketches': len(ws.sketches), 'calls': calls, 'stl': stl,
              'target_n_faces': info['n_faces'] if calls else None}
    json.dump(result, open(os.path.join(out, 'result.json'), 'w'), indent=1)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--parts', nargs='*', help='part names (default: the 20-part study sample)')
    ap.add_argument('--stl-dir', default=FRESH)
    ap.add_argument('--out', default='bench/runs/agentsk_policy')
    ap.add_argument('--max-calls', type=int, default=40)
    ap.add_argument('--max-minutes', type=float, default=30)
    ap.add_argument('--smoke', action='store_true', help='first 3 study parts into /tmp/agentsk_policy')
    a = ap.parse_args()
    parts = a.parts or study_parts(a.stl_dir)
    if a.smoke:
        parts, a.out = parts[:3], '/tmp/agentsk_policy'
    summary = {}
    for p in parts:
        out = os.path.join(a.out, p)
        if os.path.exists(os.path.join(out, 'result.json')):
            r = json.load(open(os.path.join(out, 'result.json')))
        else:
            r = run_part(os.path.join(a.stl_dir, p + '.stl'), out, a.max_calls, a.max_minutes)
        summary[p] = {k: r[k] for k in ('best_iou', 'tool_calls', 'stop', 'seconds', 'n_candidates')}
        print(f'{p[:8]} IoU {r["best_iou"]:.4f}  calls {r["tool_calls"]}  cands {r["n_candidates"]}  '
              f'{r["seconds"]}s  stop={r["stop"]}', flush=True)
    os.makedirs(a.out, exist_ok=True)
    json.dump(summary, open(os.path.join(a.out, 'summary.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()

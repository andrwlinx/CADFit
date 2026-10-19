#!/usr/bin/env python3
"""
No-LLM control for the skills toolset: a fixed policy that calls the same
skills an agent gets, under the same budget, then assembles greedily.

  1. describe_target, detect_directions
  2. section_extrude along x, y, z
  3. extract_sketch at the middle of the target along each axis, each flat-face
     normal and each detected direction; fit_extrude the 3 largest profiles of
     each plane, and fit_revolve those of the axis planes. Analysis stops 8
     calls short of the budget so that assembly always gets calls
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


def run_part(gt, out, max_calls=40, max_minutes=30.0, min_gain=1e-3, per_plane=3, reserve=8, charge_trials=False,
             agent_economy=False):
    t0 = time.time()
    ws = SkillWorkspace(gt, os.path.join(out, 'work'))
    calls = []

    def call(name, assembly=False, **args):
        # Analysis may not use the last `reserve` calls: they are kept for assembly.
        if len(calls) >= max_calls - (0 if assembly else reserve) or time.time() - t0 > 60 * max_minutes:
            raise Budget()
        res = {} if name == 'trial' else getattr(ws, name)(**args)
        calls.append({'name': name, 'args': args, 't': round(time.time() - t0, 1),
                      'error': res.get('error') if isinstance(res, dict) else None})
        return res

    def assemble():
        """Greedy assembly over the candidates the skills made."""
        nonlocal trials
        cands = sorted(ws.candidates, key=lambda c: -ws.candidates[c]['iou'])
        if not cands:
            return
        call('add_candidate', assembly=True, id=cands[0])
        if agent_economy:
            return assemble_interface(cands)
        if charge_trials:
            return assemble_charged(cands)
        while True:
            base = ws._score(ws._model())
            best = (min_gain, None, None)
            for c in cands:
                m = ws.candidates[c]['_m']
                for mode in ('add', 'cut'):
                    trials += 1
                    cur = ws._model()
                    sc = ws._score(cur + m if mode == 'add' else cur - m)
                    if sc - base > best[0]:
                        best = (sc - base, c, mode)
            if best[1] is None:
                return
            call('add_candidate', assembly=True, id=best[1], mode=best[2])

    def assemble_charged(cands):
        """Budget-matched assembly (ledger A-040): every GT-scored trial costs one tool call
        (an agent pays at least one: add_candidate reports the new IoU), and the first
        improving trial is kept, in order of candidate IoU, adds then cuts, until no trial
        in a full pass improves or the budget is spent."""
        nonlocal trials
        used = {cands[0]}
        improved = True
        while improved:
            improved = False
            for mode in ('add', 'cut'):
                for c in cands:
                    if c in used:
                        continue
                    call('trial', assembly=True)  # charged like a tool call
                    trials += 1
                    m = ws.candidates[c]['_m']
                    base = ws._score(ws._model())
                    cur = ws._model()
                    if ws._score(cur + m if mode == 'add' else cur - m) - base > min_gain:
                        call('add_candidate', assembly=True, id=c, mode=mode)
                        used.add(c)
                        improved = True

    def assemble_interface(cands):
        """Agent economy (review round 1): trials go through the agent's own tools.
        A trial is add_candidate (1 call; its reply reports the new IoU, and under
        tools v2 what the program builds); a trial that does not gain min_gain is
        undone with remove_step (1 more call). First improving trial kept, in order
        of candidate IoU, adds then cuts, until a full pass gains nothing."""
        nonlocal trials
        used = {cands[0]}
        improved = True
        while improved:
            improved = False
            for mode in ('add', 'cut'):
                for c in cands:
                    if c in used:
                        continue
                    trials += 1
                    r = call('add_candidate', assembly=True, id=c, mode=mode)
                    gain = r.get('iou_after', 0) - r.get('iou_before', 0)
                    ok = gain > min_gain and r.get('program_valid', True)
                    if ok:
                        used.add(c)
                        improved = True
                    else:
                        call('remove_step', assembly=True, step=r['step'])

    stop = 'done'
    trials = 0  # GT-scored trial unions/cuts in the greedy assembly (not tool calls; ledger A-017)
    try:
        info = call('describe_target')
        dirs = call('detect_directions')
        for axis in 'xyz':  # cheap (1-2 s) and often the strongest single candidate
            call('section_extrude', axis=axis)
        normals = [tuple(a) for a in dirs['axes']]
        for f in dirs['flat_face_normals'] + [{'normal': d['direction']} for d in dirs['other_directions']]:
            if all(abs(sum(p * q for p, q in zip(f['normal'], m))) < 0.999 for m in normals):
                normals.append(tuple(f['normal']))
        verts = ws.gt_mesh.vertices
        for k, nrm in enumerate(normals):
            proj = (verts * nrm).sum(1)
            mid = 0.5 * (proj.min() + proj.max())
            for s in call('extract_sketch', normal=list(nrm), offset=float(mid))['sketches'][:per_plane]:
                call('fit_extrude', sketch=s['id'])
                if k < 3:
                    call('fit_revolve', sketch=s['id'])
    except Budget:
        stop = 'budget'
    try:
        assemble()
    except Budget:
        stop = 'budget'
    stl = ws.export(out)
    result = {'model': 'scripted-skills-policy', 'toolset': 'skills', 'gt': gt, 'init': None, 'init_iou': 0.0,
              'best_iou': ws.best[0], 'n_steps': len(ws.best[1]),
              'sources': [s['source'] for s in ws.best[1]], 'modes': [s['mode'] for s in ws.best[1]],
              'tool_calls': len(calls), 'trial_evaluations': trials, 'stop': stop, 'seconds': round(time.time() - t0, 1),
              'n_candidates': len(ws.candidates), 'n_sketches': len(ws.sketches), 'calls': calls, 'stl': stl,
              'target_n_faces': info['n_faces'] if calls else None,
              **({'tools': 'v2', 'best_exec_iou': ws.best_exec[0], 'best_exec_valid': ws.best_exec[2]}
                 if hasattr(ws, 'best_exec') and ws.best_exec[0] >= 0 else {})}
    json.dump(result, open(os.path.join(out, 'result.json'), 'w'), indent=1)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--parts', nargs='*', help='part names (default: the 20-part study sample)')
    ap.add_argument('--stl-dir', default=FRESH)
    ap.add_argument('--out', default='bench/runs/agentsk_policy')
    ap.add_argument('--max-calls', type=int, default=40)
    ap.add_argument('--max-minutes', type=float, default=30)
    ap.add_argument('--charge-trials', action='store_true',
                    help='budget-matched control: GT-scored assembly trials count as tool calls (A-040)')
    ap.add_argument('--agent-economy', action='store_true',
                    help='assembly trials through add_candidate/remove_step, paid like an agent (round-1 review)')
    ap.add_argument('--reserve', type=int, default=8, help='calls kept for assembly')
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
            r = run_part(os.path.join(a.stl_dir, p + '.stl'), out, a.max_calls, a.max_minutes,
                         reserve=a.reserve, charge_trials=a.charge_trials, agent_economy=a.agent_economy)
        summary[p] = {k: r[k] for k in ('best_iou', 'tool_calls', 'stop', 'seconds', 'n_candidates')}
        if 'best_exec_iou' in r:
            summary[p]['best_exec_iou'] = r['best_exec_iou']
        print(f'{p[:8]} IoU {r["best_iou"]:.4f}  calls {r["tool_calls"]}  cands {r["n_candidates"]}  '
              f'{r["seconds"]}s  stop={r["stop"]}', flush=True)
    os.makedirs(a.out, exist_ok=True)
    json.dump(summary, open(os.path.join(a.out, 'summary.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()

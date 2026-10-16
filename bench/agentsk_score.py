#!/usr/bin/env python3
"""
Score the agent-skills study (ledger A-008): every episode under
bench/runs/<tag>/<model>/<toolset>/<part> and the no-LLM skills policy
(bench/runs/agentsk_policy/<part>) with the corrected judge and CAD replay
(bench/score.py), next to the pipeline references on the same parts.

A missing or failed episode scores 0 (no model, no program).

  .venv/bin/python bench/agentsk_score.py --jobs 16      # -> bench/runs/agentsk_scores.json
"""
import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'bench'))
sys.path.insert(0, os.path.join(ROOT, 'agent'))
from scripted_skills_policy import study_parts  # noqa: E402

RUNS = os.path.join(ROOT, 'bench', 'runs')
ZERO = {'iou': 0.0, 'cd': None, 'valid': False, 'iou_cad': 0.0, 'cad_built': False, 'cad_valid': False}


def score_all(jobs_list, jobs):
    """[(cond, part, gt, recon)] -> {(cond, part): record}; halves the pool on a worker death (OOM)."""
    sys.argv = sys.argv[:1]
    import score
    todo = [(c, p, gt, rec, score.JUDGE, True) for c, p, gt, rec in jobs_list]
    out = {}
    if jobs <= 1:
        for j in todo:
            out[(j[0], j[1])] = score._score_one(j)[2]
        return out
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from concurrent.futures.process import BrokenProcessPool
    while todo:
        left = {}
        try:
            with ProcessPoolExecutor(min(jobs, len(todo)), mp_context=mp.get_context('spawn'),
                                     initializer=score._init_worker) as ex:
                left = {ex.submit(score._score_one, j): j for j in todo}
                for f in as_completed(left):
                    c, p, r = f.result()
                    out[(c, p)] = r
                    print(f'{c:<34} {p[:8]} iou={r["iou"]:.4f} iou_cad={r.get("iou_cad", 0):.4f}', flush=True)
                    del left[f]
            todo = []
        except BrokenProcessPool:
            if jobs == 1:
                raise
            todo, jobs = list(left.values()), max(1, jobs // 2)
            print(f'worker died (likely OOM); rescoring {len(todo)} with {jobs} jobs', flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', default='agentsk')
    ap.add_argument('--stl-dir', default=os.path.join(ROOT, 'bench', 'cadbench', 'fresh'))
    ap.add_argument('--jobs', type=int, default=16)
    ap.add_argument('--out', default=os.path.join(RUNS, 'agentsk_scores.json'))
    a = ap.parse_args()
    parts = study_parts(a.stl_dir)
    conds, meta, jobs = {}, {}, []
    for d in sorted(glob.glob(os.path.join(RUNS, a.tag, '*', '*'))):
        if os.path.isdir(d):
            conds[os.path.relpath(d, os.path.join(RUNS, a.tag))] = d
    if os.path.isdir(os.path.join(RUNS, 'agentsk_policy')):
        conds['no-llm-policy/skills'] = os.path.join(RUNS, 'agentsk_policy')
    for cond, d in conds.items():
        for p in parts:
            ep = os.path.join(d, p)
            rj = os.path.join(ep, 'result.json')
            r = json.load(open(rj)) if os.path.exists(rj) else {}
            meta[(cond, p)] = {'tool_calls': r.get('tool_calls'), 'stop': r.get('stop', 'missing'),
                               'seconds': r.get('seconds'), 'agent_iou': r.get('best_iou'),
                               'tokens': sum((r.get('usage') or {}).values()) or None,
                               'sources': r.get('sources')}
            stl = os.path.join(ep, 'agent_model.stl')
            if os.path.exists(stl):
                jobs.append((cond, p, os.path.join(a.stl_dir, p + '.stl'), stl))
    scored = score_all(jobs, a.jobs)
    res = {c: {p: {**scored.get((c, p), ZERO), **meta[(c, p)]} for p in parts} for c in conds}
    # Pipeline references (frozen runs, same judge): arms and the best-of section control.
    ref = json.load(open(os.path.join(RUNS, 'fresh_scores.json')))
    for arm in ('fresh_beamkh', 'fresh_beamsec'):
        res[f'pipeline/{arm[6:]}'] = {p: ref[arm].get(p, ZERO) for p in parts}
    sc = json.load(open(os.path.join(RUNS, 'fresh_section_control.json')))
    res['pipeline/best_of_beam_section'] = {p: {'iou': sc[p]['best_of'], 'iou_cad': sc[p]['best_of_cad']}
                                            for p in parts}
    json.dump({'parts': parts, 'conditions': res}, open(a.out, 'w'), indent=1)
    print(f'\n{"condition":<36} {"n":>3} {"IoU":>7} {"IoU(CAD)":>9} {"CAD bad":>8} {"calls":>6}')
    for c, r in res.items():
        v = [r[p] for p in parts]
        bad = sum(not x.get('cad_valid', True) for x in v)
        calls = [x['tool_calls'] for x in v if x.get('tool_calls') is not None]
        print(f'{c:<36} {len(v):>3} {sum(x["iou"] for x in v) / len(v):7.4f} '
              f'{sum(x.get("iou_cad", 0) for x in v) / len(v):9.4f} {bad:>8} '
              f'{(sum(calls) / len(calls)) if calls else float("nan"):6.1f}')


if __name__ == '__main__':
    main()

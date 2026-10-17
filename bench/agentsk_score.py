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
from agentsk_models import MODELS  # noqa: E402
from scripted_skills_policy import study_parts  # noqa: E402

RUNS = os.path.join(ROOT, 'bench', 'runs')
ZERO = {'iou': 0.0, 'cd': None, 'valid': False, 'iou_cad': 0.0, 'cad_built': False, 'cad_valid': False}


def _capped_init(cap_gb):
    """Pool worker with an address-space cap: a judge that needs more raises
    MemoryError in that worker instead of the OOM killer taking the pool down."""
    import resource
    import score
    score._init_worker()
    cap = int(cap_gb * 2 ** 30)
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))


def _score_safe(job):
    import score
    try:
        return score._score_one(job)
    except MemoryError:
        return job[0], job[1], {'iou': 0.0, 'cd': None, 'valid': True, 'judge_error': 'MemoryError'}


def score_all(jobs_list, jobs, cap_gb=None):
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
                                     initializer=_capped_init if cap_gb else score._init_worker,
                                     initargs=(cap_gb,) if cap_gb else ()) as ex:
                left = {ex.submit(_score_safe if cap_gb else score._score_one, j): j for j in todo}
                for f in as_completed(left):
                    c, p, r = f.result()
                    out[(c, p)] = r
                    print(f'{c:<34} {p[:8]} iou={r["iou"]:.4f} iou_cad={r.get("iou_cad", 0):.4f}'
                          + (f' JUDGE ERROR {r["judge_error"]}' if 'judge_error' in r else ''), flush=True)
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
    ap.add_argument('--mem-cap-gb', type=float, default=None,
                    help='address-space cap per scoring worker; a part over it is recorded as judge_error')
    ap.add_argument('--out', default=os.path.join(RUNS, 'agentsk_scores.json'))
    ap.add_argument('--toolsets', nargs='+', default=['skills', 'code'])
    ap.add_argument('--models', nargs='+', default=None, help='default: every MODELS key (the declared panel)')
    ap.add_argument('--policy-dir', default=os.path.join(RUNS, 'agentsk_policy'),
                    help="'' to leave the policy out; references are always added")
    a = ap.parse_args()
    parts = study_parts(a.stl_dir)
    conds, meta, jobs = {}, {}, []
    # The declared panel (ledger A-004 x A-003), whether or not a run produced anything:
    # a model whose server never came up scores 0 on every part instead of vanishing.
    for key in sorted(a.models or MODELS):
        for toolset in a.toolsets:
            conds[f'{key}/{toolset}'] = os.path.join(RUNS, a.tag, key, toolset)
    if a.policy_dir:
        conds['no-llm-policy/skills'] = a.policy_dir
    extra = [d for d in glob.glob(os.path.join(RUNS, a.tag, '*', '*'))
             if os.path.isdir(d) and os.path.relpath(d, os.path.join(RUNS, a.tag)) not in conds]
    if extra:
        print(f'note: not in the declared panel, not scored: {extra}')
    for cond, d in conds.items():
        for p in parts:
            ep = os.path.join(d, p)
            rj = os.path.join(ep, 'result.json')
            r = json.load(open(rj)) if os.path.exists(rj) else {}
            meta[(cond, p)] = {'tool_calls': r.get('tool_calls'), 'stop': r.get('stop', 'missing'),
                               'seconds': r.get('seconds'), 'agent_iou': r.get('best_iou'),
                               'tokens': sum((r.get('usage') or {}).values()) or None,
                               'sources': r.get('sources'), 'trial_evaluations': r.get('trial_evaluations')}
            stl = os.path.join(ep, 'agent_model.stl')
            if os.path.exists(stl):
                jobs.append((cond, p, os.path.join(a.stl_dir, p + '.stl'), stl))
    scored = score_all(jobs, a.jobs, a.mem_cap_gb)
    # Parts over the per-worker cap: score them again one at a time, uncapped (whole job memory).
    heavy = [j for j in jobs if 'judge_error' in scored[(j[0], j[1])]]
    if heavy:
        print(f'rescoring {len(heavy)} over the memory cap one at a time, uncapped', flush=True)
        scored.update(score_all(heavy, 1))
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
        bad = sum(not x['cad_valid'] for x in v if 'cad_valid' in x) if any('cad_valid' in x for x in v) else 'n/a'
        calls = [x['tool_calls'] for x in v if x.get('tool_calls') is not None]
        print(f'{c:<36} {len(v):>3} {sum(x["iou"] for x in v) / len(v):7.4f} '
              f'{sum(x.get("iou_cad", 0) for x in v) / len(v):9.4f} {str(bad):>8} '
              f'{(sum(calls) / len(calls)) if calls else float("nan"):6.1f}')


if __name__ == '__main__':
    main()

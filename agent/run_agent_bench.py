#!/usr/bin/env python3
"""
Run the LLM agent over the parts of a --keep-history pipeline run, for several
models and two modes, then score everything with bench/score.py's judge.

  scratch: empty start; the agent has the pipeline's candidate pool + its own code.
  refine:  starts from the pipeline's final reconstruction.

  .venv/bin/python agent/run_agent_bench.py --prep bench/runs/agentprep_beam \
      --stl-dir bench/cadbench/test --models deepseek/deepseek-v4-pro z-ai/glm-5.3 \
      --modes scratch refine --tag agent1

Outputs bench/runs/<tag>/<model>/<mode>/<part>/ (see agent_loop.py) and
bench/runs/<tag>/scores.json; the pipeline's own result is scored as 'pipeline'.
Parts already finished are skipped, so the command can be re-run to resume.
"""
import argparse
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'bench'))
FINAL = 'best_greedy_parallel_iterative'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--prep', required=True, help='--keep-history run folder (one subfolder per part)')
    ap.add_argument('--stl-dir', required=True, help='original target STLs')
    ap.add_argument('--models', nargs='+', required=True)
    ap.add_argument('--modes', nargs='+', default=['scratch', 'refine'], choices=['scratch', 'refine'])
    ap.add_argument('--parts', nargs='*', help='subset of part names (default: all in --prep)')
    ap.add_argument('--tag', required=True)
    ap.add_argument('--max-calls', type=int, default=40)
    ap.add_argument('--max-minutes', type=float, default=20)
    ap.add_argument('--score-only', action='store_true')
    a, extra = ap.parse_known_args()

    parts = a.parts or sorted(os.path.basename(os.path.dirname(p))
                              for p in glob.glob(os.path.join(a.prep, '*', 'final_iou.json')))
    base = os.path.join(ROOT, 'bench', 'runs', a.tag)
    if not a.score_only:
        for model in a.models:
            for mode in a.modes:
                for part in parts:
                    out = os.path.join(base, model.replace('/', '__'), mode, part)
                    if os.path.exists(os.path.join(out, 'result.json')):
                        continue
                    cands = os.path.join(a.prep, part)
                    cmd = [sys.executable, os.path.join(ROOT, 'agent', 'agent_loop.py'),
                           '--gt', os.path.join(a.stl_dir, part + '.stl'), '--cands', cands,
                           '--model', model, '--out', out, '--max-calls', str(a.max_calls),
                           '--max-minutes', str(a.max_minutes)] + extra
                    if mode == 'refine':
                        cmd += ['--init', os.path.join(cands, FINAL + '.py')]
                    print(f'== {model} {mode} {part}', flush=True)
                    os.makedirs(out, exist_ok=True)
                    with open(os.path.join(out, 'stdout.txt'), 'w') as log:
                        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
                    print(open(os.path.join(out, 'stdout.txt')).read().strip().splitlines()[-1][:200], flush=True)

    sys.argv = [sys.argv[0]]
    import score  # judge = exact robust IoU (CADBench GTs are watertight)
    recon = {'pipeline': {p: os.path.join(a.prep, p, FINAL + '.stl') for p in parts}}
    for d in sorted(glob.glob(os.path.join(base, '*', '*'))):
        if os.path.isdir(d):
            arm = os.path.relpath(d, base)
            recon[arm] = {p: os.path.join(d, p, 'agent_model.stl') for p in parts}
    scores = {}
    for arm, files in recon.items():
        res = {}
        for p, f in files.items():
            gt = os.path.join(a.stl_dir, p + '.stl')
            meta = {}
            rj = os.path.join(os.path.dirname(f), 'result.json')
            if os.path.exists(rj):
                r = json.load(open(rj))
                meta = {k: r.get(k) for k in ('tool_calls', 'stop', 'seconds', 'cost_usd', 'n_steps', 'init_iou')}
                meta['tokens'] = sum((r.get('usage') or {}).values())
            if not os.path.exists(f):
                res[p] = {'iou': 0.0, 'cd': None, 'valid': False, **meta}
                continue
            s = score.judge(gt, f)
            s['cd'] = score.chamfer(gt, f)
            res[p] = {**s, 'valid': True, **meta}
            print(f'{arm:<45} {p[:20]:<20} iou={s["iou"]:.4f} cd={s["cd"]:.4f}', flush=True)
        scores[arm] = res
    json.dump(scores, open(os.path.join(base, 'scores.json'), 'w'), indent=1)
    print()
    pipe = scores['pipeline']
    for arm, res in scores.items():
        common = [p for p in parts if p in res]
        if not common:
            continue
        m = sum(res[p]['iou'] for p in common) / len(common)
        mp = sum(pipe[p]['iou'] for p in common) / len(common)
        wins = sum(res[p]['iou'] > pipe[p]['iou'] + 1e-3 for p in common)
        losses = sum(res[p]['iou'] < pipe[p]['iou'] - 1e-3 for p in common)
        cost = sum(res[p].get('cost_usd') or 0 for p in common)
        print(f'{arm:<45} n={len(common):2d} IoU {m:.4f} (pipeline {mp:.4f}) W/L {wins}/{losses} '
              f'invalid {sum(not res[p]["valid"] for p in common)} cost ${cost:.2f}')


if __name__ == '__main__':
    main()

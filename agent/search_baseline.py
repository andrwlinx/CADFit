#!/usr/bin/env python3
"""
Equal-time scripted search: the agent's refine setting without an LLM.

Starts from the pipeline's final model in a CadWorkspace (same candidate pool,
same IoU, same best-model retention as agent_loop.py) and runs best-improvement
local search until the time budget ends or no move helps. Moves: add any
candidate (union), cut any candidate, remove any step. This is the control for
"does the LLM's judgement beat more search over the same tools?".

Writes <out>/agent_model.{stl,py} and result.json like agent_loop.py, so
run_agent_bench.py scores it as one more arm (put it under bench/runs/<tag>/search/refine/).

  python agent/search_baseline.py --gt target.stl --cands <prep part> --init <prep part>/best_greedy_parallel_iterative.py \
      --out bench/runs/<tag>/search/refine/<part> --max-minutes 20
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cad_tools import CadWorkspace  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--gt', required=True)
    ap.add_argument('--cands', required=True)
    ap.add_argument('--init', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--max-minutes', type=float, default=20)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    deadline = t0 + 60 * a.max_minutes
    ws = CadWorkspace(a.gt, os.path.join(a.out, 'work'), a.cands, a.init)
    init_iou = ws.best[0]
    rounds = evals = 0
    stop = 'time'  # loading the pool counts against the budget, as in agent_loop.py
    while time.time() < deadline:
        stop = 'converged'
        cur = ws._score(ws._model())
        best = (cur + 1e-6, None)
        moves = [('add', c) for c in ws.candidates] + [('cut', c) for c in ws.candidates] \
            + [('remove', i) for i in range(len(ws.steps))]
        for kind, x in moves:
            if time.time() >= deadline:
                stop = 'time'
                break
            evals += 1
            if kind == 'remove':
                trial = [s for i, s in enumerate(ws.steps) if i != x]
            else:
                trial = ws.steps + [{'mode': kind, 'm': ws.candidates[x]['_m']}]
            s = ws._score(ws._model(trial))
            if s > best[0]:
                best = (s, (kind, x))
        if stop == 'time' or best[1] is None:
            break
        kind, x = best[1]
        ws.remove_step(x) if kind == 'remove' else ws.add_candidate(x, kind)
        rounds += 1
    stl = ws.export(a.out)
    result = {'model': 'search', 'gt': a.gt, 'init': a.init, 'init_iou': init_iou, 'best_iou': ws.best[0],
              'n_steps': len(ws.best[1]), 'moves_taken': rounds, 'evaluations': evals, 'stop': stop,
              'seconds': round(time.time() - t0, 1), 'stl': stl}
    json.dump(result, open(os.path.join(a.out, 'result.json'), 'w'), indent=1)
    print(f'done: best IoU {ws.best[0]:.4f} (init {init_iou:.4f}), {rounds} moves, {evals} evals, '
          f'stop={stop}, {result["seconds"]}s')


if __name__ == '__main__':
    main()

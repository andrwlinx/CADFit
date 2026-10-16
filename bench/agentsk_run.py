#!/usr/bin/env python3
"""
Run agent episodes (agent/agent_loop.py) for one model and one or more
toolsets over a set of parts, several at once against one model server.
An episode whose result.json exists is skipped, so a cut-off Slurm job resumes.

  .venv/bin/python bench/agentsk_run.py --model-key gptoss-20b --toolsets skills code \
      --tag agentsk --jobs 8 --base-url http://127.0.0.1:8000/v1

Layout: bench/runs/<tag>/<model-key>/<toolset>/<part>/{result.json, agent_model.*, transcript.jsonl, stdout.txt}
"""
import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'bench'))
sys.path.insert(0, os.path.join(ROOT, 'agent'))
from agentsk_models import MODELS  # noqa: E402
from scripted_skills_policy import study_parts  # noqa: E402


def episode(a, m, toolset, part):
    out = os.path.join(ROOT, 'bench', 'runs', a.tag, a.model_key, toolset, part)
    if os.path.exists(os.path.join(out, 'result.json')):
        return part, toolset, 'cached'
    os.makedirs(out, exist_ok=True)
    cmd = [sys.executable, os.path.join(ROOT, 'agent', 'agent_loop.py'), '--toolset', toolset,
           '--model', m['hf'], '--base-url', a.base_url, '--gt', os.path.join(a.stl_dir, part + '.stl'),
           '--out', out, '--max-calls', str(a.max_calls), '--max-minutes', str(a.max_minutes),
           '--temperature', str(m['temperature']), '--max-tokens', str(a.max_tokens),
           '--keep-tool-results', str(a.keep_tool_results), '--extra-body', json.dumps(m['body'])]
    t0 = time.time()
    with open(os.path.join(out, 'stdout.txt'), 'w') as log:
        rc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT,
                            env=dict(os.environ, AGENT_API_KEY=os.environ.get('AGENT_API_KEY', 'local'))).returncode
    tail = open(os.path.join(out, 'stdout.txt')).read().strip().splitlines()[-1:] or ['']
    return part, toolset, f'rc={rc} {time.time() - t0:.0f}s {tail[0][:150]}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model-key', required=True, choices=sorted(MODELS))
    ap.add_argument('--toolsets', nargs='+', default=['skills', 'code'], choices=['skills', 'code'])
    ap.add_argument('--parts', nargs='*', help='default: the 20-part study sample (ledger A-005)')
    ap.add_argument('--stl-dir', default=os.path.join(ROOT, 'bench', 'cadbench', 'fresh'))
    ap.add_argument('--tag', default='agentsk')
    ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--base-url', default='http://127.0.0.1:8000/v1')
    ap.add_argument('--max-calls', type=int, default=40)
    ap.add_argument('--max-minutes', type=float, default=30)
    ap.add_argument('--max-tokens', type=int, default=16384)
    ap.add_argument('--keep-tool-results', type=int, default=6)
    a = ap.parse_args()
    m = MODELS[a.model_key]
    parts = a.parts or study_parts(a.stl_dir)
    # Interleave toolsets so a job cut off by the time limit leaves both half done, not one.
    todo = [(t, p) for p in parts for t in a.toolsets]
    print(f'{a.model_key}: {len(todo)} episodes, {a.jobs} at a time', flush=True)
    status = {}
    with ThreadPoolExecutor(a.jobs) as ex:
        for f in as_completed([ex.submit(episode, a, m, t, p) for t, p in todo]):
            part, toolset, msg = f.result()
            status[f'{toolset}/{part}'] = msg
            print(f'[{time.strftime("%H:%M:%S")}] {toolset:6s} {part[:8]} {msg}', flush=True)
    base = os.path.join(ROOT, 'bench', 'runs', a.tag, a.model_key)
    done = {k: os.path.exists(os.path.join(base, k, 'result.json')) for k in status}
    json.dump({'model': m['hf'], 'episodes': len(todo), 'with_result': sum(done.values()), 'status': status},
              open(os.path.join(base, 'summary.json'), 'w'), indent=1)
    print(f'{sum(done.values())}/{len(todo)} episodes have a result', flush=True)


if __name__ == '__main__':
    main()

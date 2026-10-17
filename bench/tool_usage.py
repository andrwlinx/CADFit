#!/usr/bin/env python3
"""Tool calls per episode by tool name, per model, skills toolset (paper App. J) -> results/tool_usage.json.
Counted from transcript.jsonl (role 'tool' records), over episodes with a transcript."""
import collections
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAG = sys.argv[1] if len(sys.argv) > 1 else 'agentsk'
PARTS = set(json.load(open(os.path.join(ROOT, 'bench', 'runs', 'agentsk_scores.json')))['parts'])
out = {}
for mdir in sorted(glob.glob(os.path.join(ROOT, 'bench', 'runs', TAG, '*', 'skills'))):
    model = os.path.basename(os.path.dirname(mdir))
    tot, err, n = collections.Counter(), 0, 0
    for t in glob.glob(os.path.join(mdir, '*', 'transcript.jsonl')):
        if os.path.basename(os.path.dirname(t)) not in PARTS:  # e.g. kept copies of failed first attempts
            continue
        n += 1
        for line in open(t):
            m = json.loads(line)
            if m.get('role') == 'tool':
                tot[m.get('name')] += 1
                try:
                    err += 'error' in json.loads(m['content'])
                except (json.JSONDecodeError, TypeError):
                    pass
    out[model] = {'episodes': n, 'per_episode': {k: v / n for k, v in sorted(tot.items())},
                  'calls_per_episode': sum(tot.values()) / n, 'tool_errors': err, 'tool_calls': sum(tot.values())}
json.dump(out, open(os.path.join(ROOT, 'results', 'tool_usage.json'), 'w'), indent=1)
for k, v in out.items():
    print(k, v['episodes'], round(v['calls_per_episode'], 1), {t: round(x, 1) for t, x in v['per_episode'].items()})

#!/usr/bin/env python3
"""Trace evidence for why Qwen3.8 code episodes stopped with 'no tool call' (paper App. G).

The loop (agent/agent_loop.py) sends 'Your reply hit the token limit before you called a tool...'
only when the model's reply ended with finish_reason == 'length'. For every episode whose stop is
'no tool call', record how many such nudges it got, the last user message, and the length of the
final reasoning block.  -> results/qwen38_traces.json
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAG = sys.argv[1] if len(sys.argv) > 1 else 'agentsk'
out = {}
for t in ('code', 'skills'):
    rows = []
    for d in sorted(glob.glob(os.path.join(ROOT, 'bench', 'runs', TAG, 'qwen38-27b', t, '*'))):
        r = json.load(open(os.path.join(d, 'result.json')))
        if r.get('stop') != 'no tool call':
            continue
        msgs = [json.loads(line) for line in open(os.path.join(d, 'transcript.jsonl'))]
        users = [m.get('content') or '' for m in msgs if m.get('role') == 'user']
        reasons = [len(m.get('content') or '') for m in msgs if m.get('role') == 'reasoning']
        rows.append({'part': os.path.basename(d),
                     'token_limit_nudges': sum('hit the token limit' in u for u in users),
                     'last_nudge_is_token_limit': bool(users) and 'hit the token limit' in users[-1],
                     'final_reasoning_chars': reasons[-1] if reasons else 0,
                     'final_reply_content_chars': len(msgs[-1].get('content') or '')})
    out[t] = {'episodes_no_tool_call': len(rows),
              'all_last_nudge_token_limit': all(x['last_nudge_is_token_limit'] for x in rows),
              'final_reasoning_chars_min': min((x['final_reasoning_chars'] for x in rows), default=None),
              'final_reasoning_chars_max': max((x['final_reasoning_chars'] for x in rows), default=None),
              'episodes': rows}
os.makedirs(os.path.join(ROOT, 'results'), exist_ok=True)
json.dump(out, open(os.path.join(ROOT, 'results', 'qwen38_traces.json'), 'w'), indent=1)
print({t: {k: v for k, v in o.items() if k != 'episodes'} for t, o in out.items()})

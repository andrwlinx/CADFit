#!/usr/bin/env python3
"""
LLM agent that reconstructs a CAD model of a target mesh using CADFit's stages
as tools (agent/cad_tools.py), through any OpenAI-compatible chat API with tool
calling (OpenRouter by default).

  export OPENROUTER_API_KEY=...
  .venv/bin/python agent/agent_loop.py --gt part.stl --cands <keep-history part dir> \
      --model qwen/qwen3-coder --out bench/runs/agent_qwen3/<part>

Other endpoints: --base-url http://host:8000/v1 (vLLM/Ollama/Together...) and
the key in AGENT_API_KEY.

--init <script.py> starts from an existing reconstruction (e.g. the pipeline's
best_greedy_parallel_iterative.py) so the agent refines it; otherwise it
starts from an empty model.

Writes <out>/agent_model.stl + agent_model.py (best model seen), result.json
and transcript.jsonl.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cad_tools import CadWorkspace, openai_tools  # noqa: E402

SYSTEM = """You are a CAD engineer. Your job: build a solid CAD model that matches a target 3D part as closely \
as possible, measured by volumetric IoU (intersection over union) against the target.

You cannot see the target. You learn about it only through tools:
- describe_target: size, volume, and the flat faces (directions and plane positions).
- section: exact cross-section polygons of the target (and of your model) in any axis-aligned plane.
- list_candidates / show_candidate: solids that the CADFit pipeline already fitted to the target by slicing it \
into sketches and extruding/revolving them. precision near 1 means the candidate lies inside the target.
- add_candidate / add_code: append a solid to the model as a union ('add') or a difference ('cut').
- evaluate: current IoU and where material is missing or extra.
- remove_step, list_steps, finish.

Coordinates: everything is in the normalized frame (the target is centered and scaled so its largest extent \
spans [-1, 1]). Your CadQuery code (cq and math are imported) must assign the final solid to `result`, e.g.
    result = cq.Workplane('XY').box(1.2, 0.8, 0.1).translate((0, 0, 0.35))
    result = cq.Workplane('XY', origin=(0, 0, -0.2)).circle(0.3).extrude(0.4)
    result = cq.Workplane('XZ').polyline([(0,0),(0.5,0),(0.5,0.2),(0,0.2)]).close().revolve(360, (0,0,0), (0,1,0))

Good strategy: describe the target, look at candidates and sections, build the main body first, then add features \
and cut holes/pockets, checking evaluate after changes and removing steps that lower IoU. The best model seen at \
any point is kept, so experimenting is safe. Work efficiently: you have a limited number of tool calls. Call \
finish when you cannot improve further."""


def chat(base_url, key, model, messages, tools, temperature, max_tokens, retries=5, extra=None, deadline=None):
    body = json.dumps({'model': model, 'messages': messages, 'tools': tools, 'tool_choice': 'auto',
                       'temperature': temperature, 'max_tokens': max_tokens, **(extra or {})}).encode()
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {key}',
               'X-Title': 'CADFit agent'}
    for attempt in range(retries):
        # A request may not run past the session deadline (runs used to overrun
        # 20 min by up to 5 min: the deadline was only checked between requests).
        left = 900 if deadline is None else min(900, deadline - time.time())
        if left <= 1:
            raise TimeoutError('session deadline reached')
        req = urllib.request.Request(base_url.rstrip('/') + '/chat/completions', body, headers)
        try:
            with urllib.request.urlopen(req, timeout=left) as r:  # a thinking model's turn can run minutes
                out = json.loads(r.read())
            if 'choices' in out and out['choices']:
                return out
            err = out.get('error', out)
        except urllib.error.HTTPError as e:
            err = f'HTTP {e.code}: {e.read()[:500]!r}'
            if e.code in (400, 401, 402, 403, 404):
                raise RuntimeError(err)
        except Exception as e:  # network / timeout / bad JSON
            err = repr(e)
        print(f'  [api] attempt {attempt + 1} failed: {str(err)[:300]}', flush=True)
        wait = min(60, 5 * 2 ** attempt)
        if deadline is not None and time.time() + wait >= deadline:
            raise TimeoutError('session deadline reached')
        time.sleep(wait)
    raise RuntimeError(f'API failed after {retries} attempts: {err}')


def text_tool_calls(content, names):
    """Tool calls an open model wrote as JSON in its text instead of the API's
    tool_calls field (Qwen2.5-Coder under vLLM's hermes parser emits
    `<response>{"name": ..., "arguments": {...}}</response>`)."""
    dec, calls, i = json.JSONDecoder(), [], 0
    while (i := content.find('{', i)) >= 0:
        try:
            obj, end = dec.raw_decode(content, i)
        except json.JSONDecodeError:
            i += 1
            continue
        if isinstance(obj, dict) and obj.get('name') in names:
            args = obj.get('arguments', obj.get('parameters', {}))
            calls.append({'id': f'text_{len(calls)}', 'type': 'function',
                          'function': {'name': obj['name'],
                                       'arguments': args if isinstance(args, str) else json.dumps(args)}})
        i = end
    return calls


def _short(text, n=300):
    return text if len(text) <= n else text[:n] + ' ...[truncated]'


def _short_call(tc):
    """Tool call with long string arguments (code) cut, still valid JSON."""
    try:
        args = json.loads(tc['function']['arguments'] or '{}')
    except json.JSONDecodeError:
        return tc
    args = {k: _short(v) if isinstance(v, str) else v for k, v in args.items()}
    return dict(tc, function=dict(tc['function'], arguments=json.dumps(args)))


def compact(messages, keep):
    """Messages as sent to the model: everything before the last `keep` tool
    results (tool output, assistant text, code in tool calls) is cut short, so
    long sessions fit a small context window. The transcript keeps everything."""
    if not keep:
        return messages
    tool_idx = [i for i, m in enumerate(messages) if m['role'] == 'tool']
    if len(tool_idx) <= keep:
        return messages
    cut = tool_idx[-keep]
    while cut > 0 and messages[cut]['role'] != 'assistant':  # keep the call with its result
        cut -= 1
    out = []
    for i, m in enumerate(messages):
        if i >= cut or m['role'] in ('system', 'user'):
            out.append(m)
        elif m['role'] == 'tool':
            out.append(dict(m, content=_short(m['content'])))
        else:
            m = dict(m, content=_short(m.get('content') or ''))
            if m.get('tool_calls'):
                m['tool_calls'] = [_short_call(tc) for tc in m['tool_calls']]
            out.append(m)
    return out


def call_tool(ws, name, args):
    if name == 'finish':
        return {'ok': True}
    fn = getattr(ws, name, None)
    if fn is None or name.startswith('_'):
        return {'error': f'unknown tool {name}'}
    try:
        return fn(**args)
    except TypeError as e:
        return {'error': f'bad arguments: {e}'}
    except Exception as e:
        return {'error': f'{type(e).__name__}: {e}'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--gt', required=True)
    ap.add_argument('--cands', help='part folder of a --keep-history pipeline run')
    ap.add_argument('--init', help='CadQuery script to start from (refine mode)')
    ap.add_argument('--model', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--base-url', default=os.environ.get('AGENT_BASE_URL', 'https://openrouter.ai/api/v1'))
    ap.add_argument('--max-calls', type=int, default=40, help='tool-call budget')
    ap.add_argument('--max-minutes', type=float, default=20)
    ap.add_argument('--temperature', type=float, default=0.2)
    ap.add_argument('--max-tokens', type=int, default=4096)
    ap.add_argument('--keep-tool-results', type=int, default=0,
                    help='send only the last N tool results in full (0 = all); for small-context local models')
    ap.add_argument('--extra-body', type=json.loads, default=None,
                    help='JSON merged into each request, e.g. sampling settings or '
                         '{"chat_template_kwargs": {"enable_thinking": false}} for Qwen3.x')
    a = ap.parse_args()
    key = os.environ.get('AGENT_API_KEY') or os.environ.get('OPENROUTER_API_KEY')
    if not key:
        sys.exit('set OPENROUTER_API_KEY (or AGENT_API_KEY for another endpoint)')

    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    ws = CadWorkspace(a.gt, os.path.join(a.out, 'work'), a.cands, a.init)
    init_iou = ws.best[0]
    tools = openai_tools()
    tool_names = {t['function']['name'] for t in tools}
    user = (f'Build a CAD model of the target. Budget: {a.max_calls} tool calls.'
            + (f' The model already holds a reconstruction from the CADFit pipeline (IoU {init_iou:.4f}) as '
               'step 0; improve on it.' if a.init else ''))
    messages = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': user}]
    log = open(os.path.join(a.out, 'transcript.jsonl'), 'w')
    for m in messages:
        log.write(json.dumps(m) + '\n')

    calls = nudges = 0
    keep = a.keep_tool_results
    usage = {'prompt_tokens': 0, 'completion_tokens': 0}
    cost = 0.0
    stop = 'budget'
    deadline = t0 + 60 * a.max_minutes
    while calls < a.max_calls and time.time() < deadline:
        try:
            resp = chat(a.base_url, key, a.model, compact(messages, keep), tools,
                        a.temperature, a.max_tokens, extra=a.extra_body, deadline=deadline)
        except TimeoutError:
            stop = 'time'
            break
        except RuntimeError as e:
            # Context full: send fewer tool results in full and retry.
            if 'maximum context length' in str(e) and keep != 1:
                keep = max(1, (keep or 8) // 2)
                print(f'  [context] full; now keeping {keep} tool results', flush=True)
                continue
            stop = f'api error: {e}'
            break
        u = resp.get('usage') or {}
        for k in usage:
            usage[k] += u.get(k, 0) or 0
        cost += float(u.get('cost', 0) or 0)
        msg = resp['choices'][0]['message']
        truncated = resp['choices'][0].get('finish_reason') == 'length'
        reasoning = msg.get('reasoning_content') or msg.get('reasoning')
        if reasoning:  # transcript only: past reasoning is not sent back
            log.write(json.dumps({'role': 'reasoning', 'content': reasoning}) + '\n')
        msg = {k: v for k, v in msg.items() if k in ('role', 'content', 'tool_calls') and v is not None}
        msg.setdefault('content', '')
        if not msg.get('tool_calls') and msg['content']:
            msg['tool_calls'] = text_tool_calls(msg['content'], tool_names) or None
            if not msg['tool_calls']:
                del msg['tool_calls']
        messages.append(msg)
        log.write(json.dumps(msg) + '\n')
        tcs = msg.get('tool_calls') or []
        if not tcs:
            if nudges >= 2:
                stop = 'no tool call'
                break
            nudges += 1
            # Open models often paste code into their reply instead of running it.
            # Thinking models can also spend the whole reply on reasoning.
            text = ('Your reply hit the token limit before you called a tool. '
                    'Think briefly, then call a tool now.' if truncated else
                    'Your code was not run: code in a reply does nothing. Call add_code with it.'
                    if '```' in msg['content'] else
                    'Continue by calling a tool, or call finish if you are done.')
            nudge = {'role': 'user', 'content': text}
            messages.append(nudge)
            log.write(json.dumps(nudge) + '\n')
            continue
        done = False
        for tc in tcs:
            if time.time() >= deadline:  # tool calls returned at the deadline are not run
                stop, done = 'time', True
                break
            calls += 1
            name = tc['function']['name']
            try:
                args = json.loads(tc['function'].get('arguments') or '{}') or {}
            except json.JSONDecodeError as e:
                args, res = None, {'error': f'arguments are not valid JSON: {e}'}
            if args is not None:
                res = call_tool(ws, name, args)
            txt = json.dumps(res)
            if len(txt) > 6000:
                txt = txt[:6000] + ' ...[truncated]'
            tm = {'role': 'tool', 'tool_call_id': tc.get('id', ''), 'content': txt}
            messages.append(tm)
            log.write(json.dumps({**tm, 'name': name, 'args': args}) + '\n')
            log.flush()
            iou_now = ws._score(ws._model())
            print(f'  [{calls:2d}] {name}({json.dumps(args)[:80]}) -> IoU {iou_now:.4f}'
                  + (f'  ERR {str(res.get("error"))[:100]}' if isinstance(res, dict) and 'error' in res else ''),
                  flush=True)
            if name == 'finish':
                done = True
        if done:
            stop = 'finish' if stop != 'time' else stop
            break

    stl = ws.export(a.out)
    result = {'model': a.model, 'gt': a.gt, 'init': a.init, 'init_iou': init_iou,
              'best_iou': ws.best[0], 'n_steps': len(ws.best[1]),
              'sources': [s['source'] for s in ws.best[1]], 'modes': [s['mode'] for s in ws.best[1]],
              'tool_calls': calls, 'stop': stop, 'seconds': round(time.time() - t0, 1),
              'usage': usage, 'cost_usd': round(cost, 4), 'stl': stl,
              'iou_trace': [(round(t - t0, 1), round(s, 4), n) for t, s, n in ws.history]}
    json.dump(result, open(os.path.join(a.out, 'result.json'), 'w'), indent=1)
    print(f'done: best IoU {ws.best[0]:.4f} (init {init_iou:.4f}), {calls} calls, stop={stop}, '
          f'{result["seconds"]}s, tokens {usage}, ${cost:.4f}')


if __name__ == '__main__':
    main()

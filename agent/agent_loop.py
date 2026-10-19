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
import re
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cad_tools import CadWorkspace  # noqa: E402
from skills import SkillWorkspace, openai_tools  # noqa: E402

_INTRO = """You are a CAD engineer. Your job: build a solid CAD model that matches a target 3D part as closely \
as possible, measured by volumetric IoU (intersection over union) against the target.

You cannot see the target. You learn about it only through tools:
- describe_target: size, volume, and the flat faces (directions and plane positions).
- section: exact cross-section polygons of the target (and of your model) in any axis-aligned plane.
"""
_TOOLS = {
    'pool': """\
- list_candidates / show_candidate: solids that the CADFit pipeline already fitted to the target by slicing it \
into sketches and extruding/revolving them. precision near 1 means the candidate lies inside the target.
- add_candidate / add_code: append a solid to the model as a union ('add') or a difference ('cut').
""",
    'skills': """\
- CADFit skills, the stages of a CAD reconstruction pipeline, which you run yourself: detect_directions (likely \
extrusion directions), extract_sketch (slice the target at a plane into sketch profiles fitted with lines and arcs), \
fit_extrude / fit_revolve (turn a sketch into extrusion / revolve solids that match the target), section_extrude \
(extrude a whole cross-section through the part). Each solid they make becomes a scored candidate: \
list_candidates / show_candidate show them; precision near 1 means the candidate lies inside the target.
- add_candidate / add_code: append a solid to the model as a union ('add') or a difference ('cut').
""",
    'code': """\
- add_code: append a solid built by your CadQuery code to the model as a union ('add') or a difference ('cut').
""",
    'codesec': """\
- section_extrude: a CADFit stage that extrudes the target's whole cross-section at a plane through the full \
extent of the part. Each solid it makes becomes a scored candidate: list_candidates / show_candidate show them; \
precision near 1 means the candidate lies inside the target.
- add_candidate / add_code: append a solid to the model as a union ('add') or a difference ('cut').
""",
}
_OUTRO = """\
- evaluate: current IoU and where material is missing or extra.
- remove_step, list_steps, finish.

Coordinates: everything is in the normalized frame (the target is centered and scaled so its largest extent \
spans [-1, 1]). Your CadQuery code (cq and math are imported) must assign the final solid to `result`, e.g.
    result = cq.Workplane('XY').box(1.2, 0.8, 0.1).translate((0, 0, 0.35))
    result = cq.Workplane('XY', origin=(0, 0, -0.2)).circle(0.3).extrude(0.4)
    result = cq.Workplane('XZ').polyline([(0,0),(0.5,0),(0.5,0.2),(0,0.2)]).close().revolve(360, (0,0,0), (0,1,0))

Good strategy: describe the target, {look}, build the main body first, then add features \
and cut holes/pockets, checking evaluate after changes and removing steps that lower IoU. The best model seen at \
any point is kept, so experimenting is safe. Work efficiently: you have a limited number of tool calls. Call \
finish when you cannot improve further."""
_LOOK = {'pool': 'look at candidates and sections',
         'skills': 'extract sketches on its main planes and fit them into candidates',
         'code': 'read sections to get exact profile shapes',
         'codesec': 'read sections to get exact profile shapes and extrude whole cross-sections'}


_EXEC_NOTE = """

Your model is also a CadQuery program: after every change it is executed by the CAD kernel, and replies report program_builds, program_valid and program_iou (the IoU of what the program builds). The answer kept is the best valid program, so a step that breaks the program (program_valid false) does not count until you remove or replace it."""


def system_prompt(toolset):
    from cad_tools import EXEC
    return (_INTRO + _TOOLS[toolset] + _OUTRO.replace('{look}', _LOOK[toolset])
            + (_EXEC_NOTE if EXEC else ''))


SYSTEM = system_prompt('pool')


class Scripted:
    """Model backend that replays tool calls from a JSON file (`--model scripted:<file>`):
    a list of turns, each a list of {"name", "arguments"}; finish when exhausted.
    For tests and deterministic no-LLM controls."""

    def __init__(self, path):
        self.turns = json.load(open(path))
        self.i = 0

    def __call__(self, *_, **__):
        turn = self.turns[self.i] if self.i < len(self.turns) else [{'name': 'finish', 'arguments': {}}]
        self.i += 1
        calls = [{'id': f'scripted_{self.i}_{k}', 'type': 'function',
                  'function': {'name': c['name'], 'arguments': json.dumps(c.get('arguments', {}))}}
                 for k, c in enumerate(turn)]
        return {'choices': [{'message': {'role': 'assistant', 'content': '', 'tool_calls': calls},
                             'finish_reason': 'tool_calls'}], 'usage': {}}


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


MAX_RESULT_CHARS = 8000


def _is_points(v):
    return bool(v) and all(isinstance(p, list) and p and all(isinstance(x, (int, float)) for x in p) for p in v)


def fit_json(obj, limit):
    """JSON of a tool result, at most `limit` characters and still valid JSON:
    the longest list is thinned (point lists keep every other point, other
    lists keep their first half plus an '... N more omitted' marker), then
    long strings are cut, until it fits."""
    txt = json.dumps(obj)
    if len(txt) <= limit:
        return txt
    obj = json.loads(txt)
    for _ in range(400):
        found = []

        def walk(o):
            items = o.items() if isinstance(o, dict) else enumerate(o) if isinstance(o, list) else ()
            for k, v in items:
                if isinstance(v, list) and len(v) > 2:
                    found.append((len(json.dumps(v)), id(o), o, k))
                if isinstance(v, (dict, list)):
                    walk(v)
        walk(obj)
        if not found:
            break
        _, _, cont, k = max(found, key=lambda f: f[0])
        v = cont[k]
        if _is_points(v):
            cont[k] = v[::2]
        else:
            keep = max(1, len(v) // 2)
            n = len(v) - keep
            cont[k] = v[:keep] + [f'... {n} more omitted (result too long)']
        txt = json.dumps(obj)
        if len(txt) <= limit:
            return txt

    def cut(o):
        if isinstance(o, dict):
            return {k: cut(v) for k, v in o.items()}
        if isinstance(o, list):
            return [cut(v) for v in o]
        return o[:limit // 2] + ' ...[cut]' if isinstance(o, str) and len(o) > limit // 2 else o
    txt = json.dumps(cut(obj))
    return txt if len(txt) <= limit else json.dumps({'error': 'tool result too large to show',
                                                     'preview': txt[:limit // 2]})


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


_SPECIAL = re.compile(r'<\|[a-z_]+\|>')
_CHANNEL_JUNK = ('<|channel|>commentary', '<|channel|>analysis', '<|channel|>final', '<|constrain|>json',
                 'commentary', 'analysis', 'json')


def clean_tool_name(name, names):
    """A tool name with chat-format residue mapped back to the tool it names, else unchanged.

    gpt-oss under vLLM's `openai` parser sometimes returns the harmony channel
    glued to the name ("sectioncommentary", "functions.evaluate"). Only an
    exact tool name left after stripping that residue is accepted."""
    if name in names or not isinstance(name, str):
        return name
    n = name.strip()
    if n.startswith('functions.'):
        n = n[len('functions.'):]
    changed = True
    while changed and n not in names:
        changed = False
        for junk in _CHANNEL_JUNK:
            if n.endswith(junk) and len(n) > len(junk):
                n, changed = n[:-len(junk)].rstrip(' .:<|>'), True
                break
    return n if n in names else name


def call_tool(ws, name, args, allowed=None):
    if name == 'finish':
        return {'ok': True}
    fn = getattr(ws, name, None)
    if fn is None or name.startswith('_') or (allowed is not None and name not in allowed):
        return {'error': f'unknown tool {name}'}
    try:
        return fn(**args)
    except TypeError as e:
        return {'error': f'bad arguments: {e}'}
    except Exception as e:
        return {'error': f'{type(e).__name__}: {e}'}


# Harness v2 (with tools v2): nudge counter reset after every turn with a tool
# call (v1 never reset it: 3 tool-less replies anywhere in a session ended it),
# and in-process skills (slicing, fitting) are interrupted at the deadline.
HARNESS_V2 = os.environ.get('CADFIT_AGENT_EXEC') == '1'


def call_tool_until(ws, name, args, allowed, deadline):
    """call_tool, interrupted by SIGALRM at the session deadline."""
    import signal
    left = deadline - time.time()
    if left <= 0:
        return {'error': 'session time limit reached'}

    def _alarm(*_):
        raise TimeoutError('session time limit reached during the tool call')
    old = signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, left)
    try:
        return call_tool(ws, name, args, allowed)
    except TimeoutError as e:
        return {'error': str(e)}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--gt', required=True)
    ap.add_argument('--cands', help='part folder of a --keep-history pipeline run')
    ap.add_argument('--init', help='CadQuery script to start from (refine mode)')
    ap.add_argument('--model', required=True, help='model name at --base-url, or scripted:<calls.json>')
    ap.add_argument('--out', required=True)
    ap.add_argument('--toolset', choices=['pool', 'skills', 'code', 'codesec'], default='pool',
                    help='pool: precomputed CADFit candidates (--cands); skills: the agent runs CADFit stages '
                         'itself (agent/skills.py); code: CadQuery only')
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
    scripted = Scripted(a.model.split(':', 1)[1]) if a.model.startswith('scripted:') else None
    key = os.environ.get('AGENT_API_KEY') or os.environ.get('OPENROUTER_API_KEY')
    if not key and not scripted:
        sys.exit('set OPENROUTER_API_KEY (or AGENT_API_KEY for another endpoint)')
    if a.toolset != 'pool' and (a.cands or a.init):
        sys.exit('--cands/--init belong to --toolset pool; skills and code start from an empty model')

    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    work = os.path.join(a.out, 'work')
    ws = (CadWorkspace(a.gt, work, a.cands, a.init) if a.toolset == 'pool' else
          SkillWorkspace(a.gt, work) if a.toolset in ('skills', 'codesec') else CadWorkspace(a.gt, work))
    init_iou = ws.best[0]
    if HARNESS_V2:
        ws.deadline = t0 + 60 * a.max_minutes  # tool subprocesses stop at the session deadline
    tools = openai_tools(a.toolset)
    tool_names = {t['function']['name'] for t in tools}
    user = (f'Build a CAD model of the target. Budget: {a.max_calls} tool calls.'
            + (f' The model already holds a reconstruction from the CADFit pipeline (IoU {init_iou:.4f}) as '
               'step 0; improve on it.' if a.init else ''))
    messages = [{'role': 'system', 'content': system_prompt(a.toolset)}, {'role': 'user', 'content': user}]
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
            resp = (scripted or chat)(a.base_url, key, a.model, compact(messages, keep), tools,
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
        if _SPECIAL.search(msg['content']):
            # gpt-oss can leak harmony control tokens (<|end|><|start|>assistant) into its
            # text; sent back as history they make vLLM fail every later request (HTTP 500).
            log.write(json.dumps({'role': 'harness', 'stripped_special_tokens_from': msg['content'][:2000]}) + '\n')
            msg['content'] = _SPECIAL.sub(' ', msg['content']).strip()
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
        if HARNESS_V2:
            nudges = 0  # the limit is on consecutive replies without a tool call
        for tc in tcs:
            if time.time() >= deadline:  # tool calls returned at the deadline are not run
                stop, done = 'time', True
                break
            if calls >= a.max_calls:  # several calls in one turn may not run past the budget
                stop, done = 'budget', True
                break
            calls += 1
            raw_name = tc['function']['name']
            name = clean_tool_name(raw_name, tool_names)
            if name != raw_name:
                log.write(json.dumps({'role': 'harness', 'tool_name_cleaned': [raw_name, name]}) + '\n')
            try:
                args = json.loads(tc['function'].get('arguments') or '{}') or {}
            except json.JSONDecodeError as e:
                args, res = None, {'error': f'arguments are not valid JSON: {e}'}
            if args is not None:
                res = (call_tool_until(ws, name, args, tool_names, deadline) if HARNESS_V2
                       else call_tool(ws, name, args, tool_names))
            txt = fit_json(res, MAX_RESULT_CHARS)
            tm = {'role': 'tool', 'tool_call_id': tc.get('id', ''), 'content': txt}
            messages.append(tm)
            log.write(json.dumps({**tm, 'name': name, 'args': args}) + '\n')
            log.flush()
            iou_now = ws._score(ws._model())
            print(f'  [{calls:2d}] {name}({json.dumps(args)[:80]}) -> IoU {iou_now:.4f}'
                  + (f'  ERR {str(res.get("error"))[:100]}' if isinstance(res, dict) and 'error' in res else ''),
                  flush=True)
            if name == 'finish':
                stop, done = 'finish', True
                break
        if done:
            break

    stl = ws.export(a.out)
    result = {'model': a.model, 'toolset': a.toolset, 'gt': a.gt, 'init': a.init, 'init_iou': init_iou,
              'best_iou': ws.best[0], 'n_steps': len(ws.best[1]),
              'sources': [s['source'] for s in ws.best[1]], 'modes': [s['mode'] for s in ws.best[1]],
              'tool_calls': calls, 'stop': stop, 'seconds': round(time.time() - t0, 1),
              **({'tools': 'v2', 'best_exec_iou': ws.best_exec[0], 'best_exec_valid': ws.best_exec[2],
                  'n_exec': ws.n_exec} if HARNESS_V2 else {}),
              'usage': usage, 'cost_usd': round(cost, 4), 'stl': stl,
              'iou_trace': [(round(t - t0, 1), round(s, 4), n) for t, s, n in ws.history]}
    json.dump(result, open(os.path.join(a.out, 'result.json'), 'w'), indent=1)
    print(f'done: best IoU {ws.best[0]:.4f} (init {init_iou:.4f}), {calls} calls, stop={stop}, '
          f'{result["seconds"]}s, tokens {usage}, ${cost:.4f}')


if __name__ == '__main__':
    main()

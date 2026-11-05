"""
Claude (Anthropic Messages API, official SDK) behind agent_loop's chat() interface.

agent_loop.py keeps an OpenAI-style message list and calls
`chat(base_url, key, model, messages, tools, temperature, max_tokens, extra=, deadline=)`,
expecting an OpenAI-style response dict. AnthropicChat has the same call shape.

The Claude conversation is kept here, append-only: each call converts only the
messages added since the previous call, and an assistant turn is replayed as the
exact content Claude returned (thinking blocks included). Claude Opus 5.5 and
Sonnet 5.5 reject a history whose earlier turns were edited, and agent_loop's
compact() shortens old tool results; this adapter never sends those edits.

Settings: adaptive thinking (always on for these models), effort from
`extra['effort']` (default "high"), automatic prompt caching of the growing
prefix, streaming (long thinking turns), no server-side refusal fallback (a
fallback would answer with another model inside a per-model comparison; a
refusal ends the episode instead). Temperature is not sent (these models reject
sampling parameters). max_tokens per turn is 32,000 for both Claude models
(agent_loop's --max-tokens is not used here) and the full native history is
kept (no compaction); both differ from the open-model harness settings.
"""
import json
import time

import anthropic

# $/MTok: input, output, cache read, 5-minute cache write (1.25x input).
PRICES = {'claude-opus-5-5': (4.0, 20.0, 0.20, 5.0), 'claude-sonnet-5-5': (2.0, 10.0, 0.20, 2.5)}


class AnthropicChat:
    def __init__(self, model, max_tokens=32000):
        self.client = anthropic.Anthropic()  # ANTHROPIC_API_KEY from the environment
        self.model = model
        self.max_tokens = max_tokens
        self.native = []      # the Claude conversation, append-only
        self.consumed = 0     # agent_loop messages already converted
        self.last_content = None

    @staticmethod
    def tools(oai_tools):
        return [{'name': t['function']['name'], 'description': t['function'].get('description', ''),
                 'input_schema': t['function'].get('parameters') or {'type': 'object', 'properties': {}}}
                for t in oai_tools]

    def _append_new(self, messages):
        new = messages[self.consumed:]
        self.consumed = len(messages)
        i = 0
        while i < len(new):
            m = new[i]
            if m['role'] == 'system':
                i += 1
                continue
            if m['role'] == 'assistant':
                # The turn Claude produced last call, replayed unchanged.
                self.native.append({'role': 'assistant', 'content': self.last_content})
                i += 1
            elif m['role'] == 'tool':
                results = []
                while i < len(new) and new[i]['role'] == 'tool':
                    results.append({'type': 'tool_result', 'tool_use_id': new[i]['tool_call_id'],
                                    'content': new[i]['content'] or '(empty)'})
                    i += 1
                self.native.append({'role': 'user', 'content': results})
            else:
                self.native.append({'role': 'user', 'content': m['content']})
                i += 1

    def __call__(self, base_url, key, model, messages, tools, temperature, max_tokens, retries=5, extra=None,
                 deadline=None):
        system = next((m['content'] for m in messages if m['role'] == 'system'), None)
        self._append_new(messages)
        left = 900 if deadline is None else min(1800, deadline - time.time())
        if left <= 1:
            raise TimeoutError('session deadline reached')
        effort = (extra or {}).get('effort', 'high')
        try:
            with self.client.with_options(timeout=left, max_retries=retries).messages.stream(
                    model=self.model, max_tokens=self.max_tokens, system=system, messages=self.native,
                    tools=self.tools(tools), thinking={'type': 'adaptive'}, output_config={'effort': effort},
                    cache_control={'type': 'ephemeral'}) as stream:
                resp = stream.get_final_message()
        except anthropic.APITimeoutError as e:
            raise TimeoutError(str(e)) from e
        except anthropic.APIStatusError as e:
            raise RuntimeError(f'API {e.status_code}: {e.message}') from e
        except anthropic.APIConnectionError as e:
            raise RuntimeError(f'API connection: {e}') from e
        if resp.stop_reason == 'refusal':
            cat = getattr(resp.stop_details, 'category', None) if resp.stop_details else None
            raise RuntimeError(f'refusal ({cat})')
        self.last_content = resp.content
        text = ''.join(b.text for b in resp.content if b.type == 'text')
        calls = [{'id': b.id, 'type': 'function', 'function': {'name': b.name, 'arguments': json.dumps(b.input)}}
                 for b in resp.content if b.type == 'tool_use']
        u = resp.usage
        cr, cw = u.cache_read_input_tokens or 0, u.cache_creation_input_tokens or 0
        pin, pout, pcr, pcw = PRICES.get(self.model, (0, 0, 0, 0))
        cost = (u.input_tokens * pin + u.output_tokens * pout + cr * pcr + cw * pcw) / 1e6
        msg = {'role': 'assistant', 'content': text}
        if calls:
            msg['tool_calls'] = calls
        return {'choices': [{'message': msg, 'finish_reason': 'length' if resp.stop_reason == 'max_tokens' else 'stop'}],
                'usage': {'prompt_tokens': u.input_tokens + cr + cw, 'completion_tokens': u.output_tokens,
                          'cost': cost, 'cache_read_tokens': cr, 'cache_write_tokens': cw}}

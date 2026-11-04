"""Models for the agent-skills study (ledger A-004, A-009): open-weight via vLLM, Claude via its API.

Each entry: Hugging Face id, the GPU it needs, vLLM serve flags (tool-call and
reasoning parsers from the model cards), and the request extras (model-card
sampling; thinking on where the model has it).

  python bench/agentsk_models.py <key> serve   # vLLM flags, one per line
  python bench/agentsk_models.py <key> body    # JSON for agent_loop.py --extra-body
  python bench/agentsk_models.py <key> field   # any other field, e.g. hf, gpu, temperature
"""
import json
import sys

_QWEN_THINK = {'top_p': 0.95, 'top_k': 20, 'min_p': 0.0, 'presence_penalty': 0.0,
               'chat_template_kwargs': {'enable_thinking': True}}

MODELS = {
    'qwen38-27b': {'hf': 'Qwen/Qwen3.8-27B-FP8', 'gpu': 'h100', 'temperature': 1.0, 'body': _QWEN_THINK,
                   'serve': ['--reasoning-parser', 'qwen3', '--tool-call-parser', 'qwen3_xml',
                             '--language-model-only']},
    'qwen36-35b-a3b': {'hf': 'Qwen/Qwen3.6-35B-A3B-FP8', 'gpu': 'h100', 'temperature': 1.0, 'body': _QWEN_THINK,
                       'serve': ['--reasoning-parser', 'qwen3', '--tool-call-parser', 'qwen3_coder',
                                 '--language-model-only']},
    'gemma4-31b': {'hf': 'google/gemma-4-31B-it', 'gpu': 'h200', 'temperature': 1.0,
                   'body': {'top_p': 0.95, 'top_k': 64, 'chat_template_kwargs': {'enable_thinking': True}},
                   'serve': ['--reasoning-parser', 'gemma4', '--tool-call-parser', 'gemma4']},
    'gptoss-120b': {'hf': 'openai/gpt-oss-120b', 'gpu': 'h100', 'temperature': 1.0, 'body': {'top_p': 1.0},
                    'serve': ['--reasoning-parser', 'openai_gptoss', '--tool-call-parser', 'openai']},
    'gptoss-20b': {'hf': 'openai/gpt-oss-20b', 'gpu': 'h100', 'temperature': 1.0, 'body': {'top_p': 1.0},
                   'serve': ['--reasoning-parser', 'openai_gptoss', '--tool-call-parser', 'openai']},
    'devstral2-24b': {'hf': 'mistralai/Devstral-Small-2-24B-Instruct-2512', 'gpu': 'h100', 'temperature': 0.15,
                      'body': {}, 'serve': ['--tool-call-parser', 'mistral', '--tokenizer-mode', 'mistral',
                                            '--config-format', 'mistral', '--load-format', 'mistral']},
    # Closed models through the Anthropic Messages API (agent/anthropic_chat.py; ANTHROPIC_API_KEY),
    # no GPU or server. Adaptive thinking at effort high; these models take no sampling parameters.
    'sonnet55': {'hf': 'claude-sonnet-5-5', 'gpu': 'none', 'temperature': 1.0, 'body': {'effort': 'high'}, 'serve': []},
    'opus55': {'hf': 'claude-opus-5-5', 'gpu': 'none', 'temperature': 1.0, 'body': {'effort': 'high'}, 'serve': []},
}

if __name__ == '__main__':
    key, what = sys.argv[1], sys.argv[2]
    m = MODELS[key]
    if what == 'serve':
        print('\n'.join(m['serve']))
    elif what == 'body':
        print(json.dumps(m['body']))
    else:
        print(m[what])

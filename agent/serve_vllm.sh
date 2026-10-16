#!/bin/bash
# Serve an open model for agent/agent_loop.py on one GPU with vLLM's
# OpenAI-compatible server (tool calling via the hermes parser, which Qwen2.5 uses).
#
#   GPU=0 PORT=8000 agent/serve_vllm.sh [model [extra vllm args...]]
#   AGENT_API_KEY=local .venv/bin/python agent/agent_loop.py --base-url http://localhost:8000/v1 \
#       --model Qwen/Qwen2.5-Coder-14B-Instruct-AWQ ...
#
# Default model: Qwen2.5-Coder-14B-Instruct-AWQ (~10 GB weights) with a 32k
# context fits one 24 GB card. Qwen2.5-32B-Instruct-AWQ needs a smaller window,
# e.g. MAX_LEN=20480 GPU_UTIL=0.95 ... --kv-cache-dtype fp8 --enforce-eager.
# VLLM_PY points at a Python with vllm installed (separate env from CADFit's).
# Qwen3.x needs a newer vLLM (~/vllm030: 0.30.0+cu129, which runs on the
# workstation's CUDA 12.3 driver) and its own parsers, e.g.
#   VLLM_PY=~/vllm030/bin/python TOOL_PARSER=qwen3_xml MAX_LEN=32768 agent/serve_vllm.sh \
#       RedHatAI/Qwen3.8-27B-INT4 --reasoning-parser qwen3 --language-model-only --attention-backend FLASH_ATTN
# (FLASH_ATTN is prebuilt; FlashInfer would JIT-compile with the system's CUDA 12.3 nvcc.)
MODEL=${1:-Qwen/Qwen2.5-Coder-14B-Instruct-AWQ}; shift
VLLM_PY=${VLLM_PY:-$HOME/miniforge3/envs/VLLM/bin/python}
export PATH="$(dirname "$VLLM_PY"):$PATH"  # ninja etc. for kernels built at startup
CUDA_VISIBLE_DEVICES=${GPU:-0} exec "$VLLM_PY" -m vllm.entrypoints.openai.api_server \
  --model "$MODEL" --served-model-name "$MODEL" \
  --host 127.0.0.1 --port "${PORT:-8000}" --api-key "${AGENT_API_KEY:-local}" \
  --max-model-len "${MAX_LEN:-32768}" --gpu-memory-utilization "${GPU_UTIL:-0.90}" \
  --enable-auto-tool-choice --tool-call-parser "${TOOL_PARSER:-hermes}" "$@"

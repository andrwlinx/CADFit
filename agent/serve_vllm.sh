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
MODEL=${1:-Qwen/Qwen2.5-Coder-14B-Instruct-AWQ}; shift
VLLM_PY=${VLLM_PY:-$HOME/miniforge3/envs/VLLM/bin/python}
CUDA_VISIBLE_DEVICES=${GPU:-0} exec "$VLLM_PY" -m vllm.entrypoints.openai.api_server \
  --model "$MODEL" --served-model-name "$MODEL" \
  --host 127.0.0.1 --port "${PORT:-8000}" --api-key "${AGENT_API_KEY:-local}" \
  --max-model-len "${MAX_LEN:-32768}" --gpu-memory-utilization "${GPU_UTIL:-0.90}" \
  --enable-auto-tool-choice --tool-call-parser hermes "$@"

#!/bin/bash
# One model of the agent-skills study on one ORCD GPU: serve it with vLLM,
# run its episodes (bench/agentsk_run.py) in the CADFit container, stop.
# Resumable: finished episodes are skipped, so resubmit after a time-out.
#
#   sbatch --gres=gpu:h100:1 bench/agentsk_job.sh gptoss-20b [agentsk_run.py args...]
#SBATCH -p mit_normal_gpu
#SBATCH -c 32
#SBATCH --mem=240G
#SBATCH -t 06:00:00
#SBATCH -o bench/runs/agentsk_logs/%x_%j.log
set -u
KEY=$1; shift
P=/orcd/pool/007/a_lin
cd $P/cadfit
export HF_HOME=$P/cache/huggingface AGENT_API_KEY=local
PORT=$((8000 + RANDOM % 1000))
HF_ID=$(python3 bench/agentsk_models.py "$KEY" hf)
mapfile -t SERVE < <(python3 bench/agentsk_models.py "$KEY" serve)
echo "[$(date +%T)] $KEY ($HF_ID) on $(hostname) $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1), port $PORT"

$P/envs/vllm/bin/vllm serve "$HF_ID" --host 127.0.0.1 --port $PORT --api-key local \
  --max-model-len ${MAX_LEN:-65536} --gpu-memory-utilization 0.90 --enable-auto-tool-choice \
  "${SERVE[@]}" > bench/runs/agentsk_logs/vllm_${KEY}_${SLURM_JOB_ID}.log 2>&1 &
VLLM=$!
trap 'kill $VLLM 2>/dev/null' EXIT
for i in $(seq 1 180); do  # up to 30 min for download + load
  curl -sf -H "Authorization: Bearer local" http://127.0.0.1:$PORT/v1/models > /dev/null && break
  kill -0 $VLLM 2>/dev/null || { echo "vLLM exited; see vllm_${KEY}_${SLURM_JOB_ID}.log"; exit 1; }
  sleep 10
done
echo "[$(date +%T)] server ready"

module load apptainer/1.5.2
apptainer exec -B /orcd $P/envs/cadfit-sandbox $P/envs/cadfit-venv/bin/python bench/agentsk_run.py \
  --model-key "$KEY" --base-url http://127.0.0.1:$PORT/v1 "$@"
echo "[$(date +%T)] done"

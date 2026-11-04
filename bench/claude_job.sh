#!/bin/bash
# Claude Opus/Sonnet 5.5 in the agent-skills study on ORCD CPU nodes: no model server,
# episodes call the Anthropic Messages API (agent/anthropic_chat.py) with the key in
# ~/.cadfit_keys (ANTHROPIC_API_KEY=..., mode 600). Resumable like bench/agentsk_job.sh.
#
#   sbatch -J cl_sonnet55 bench/claude_job.sh sonnet55 --toolsets code skills \
#       --stl-dir bench/cadbench/fresh2 --parts $(python3 -c "import json; d=json.load(open('bench/cadbench/fresh2_subset.json'))['parts']; print(*sum(d.values(), []))") --tag agentsk_f2
#SBATCH -p mit_normal
#SBATCH -c 32
#SBATCH --mem=128G
#SBATCH -t 12:00:00
#SBATCH --constraint=rocky8
#SBATCH -o bench/runs/agentsk_logs/%x_%j.log
set -eu
KEY=$1; shift
P=/orcd/pool/007/a_lin
cd ${CADFIT_SRC:-$P/cadfit}
set -a; . ~/.cadfit_keys; set +a
export CADFIT_AGENT_EXEC=${CADFIT_AGENT_EXEC:-1}
module load apptainer/1.5.2 2>/dev/null || export PATH=/orcd/software/core/001/pkg/apptainer/1.5.2/bin:$PATH
PY="apptainer exec -B /orcd $P/envs/cadfit-sandbox $P/envs/cadfit-venv/bin/python"
$PY -c "import cadquery, manifold3d, trimesh, scipy, shapely, anthropic" && echo "[$(date +%T)] $KEY on $(hostname), imports warm"
$PY bench/agentsk_run.py --model-key "$KEY" "$@"
echo "[$(date +%T)] done"

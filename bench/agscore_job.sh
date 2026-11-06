#!/bin/bash
# Re-judge every delivered agent program of one closed-model run tag (default: the reserved
# 40 fresh2 parts) with score.py's CAD replay (bench/agentsk_score.py), like the pipeline.
#
#   sbatch -J agscore_r1 bench/agscore_job.sh agentsk_f2_r1
#   sbatch -J agscore_tv bench/agscore_job.sh tv_v3_r0 bench/cadbench/fresh3_parts.json bench/cadbench/fresh3
#SBATCH -p mit_preemptable
#SBATCH -c 16
#SBATCH --mem=96G
#SBATCH -t 1-00:00:00
#SBATCH --constraint=rocky8
#SBATCH --exclude=node4002
#SBATCH -o bench/runs/agentsk_logs/%x_%j.log
set -eu
TAG=$1
PARTS_FILE=${2:-bench/cadbench/fresh2_subset.json}
STL_DIR=${3:-bench/cadbench/fresh2}
P=/orcd/pool/007/a_lin
cd $P/cadfit
module load apptainer/1.5.2 2>/dev/null || export PATH=/orcd/software/core/001/pkg/apptainer/1.5.2/bin:$PATH
apptainer exec -B /orcd $P/envs/cadfit-sandbox $P/envs/cadfit-venv/bin/python bench/agentsk_score.py \
  --tag $TAG --models sonnet55 opus55 --toolsets code skills \
  --parts-file $PARTS_FILE --stl-dir $STL_DIR \
  --ref-scores '' --section-control '' --policy-dir '' --jobs 4 --out bench/runs/${TAG}_scores.json

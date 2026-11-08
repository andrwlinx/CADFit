#!/bin/bash
# Common-protocol replay of one seed's delivered trim programs (bench/trim_common_replay.py).
#   sbatch -J trimcommon0 bench/trim_common_job.sh 0
#SBATCH -p mit_preemptable
#SBATCH -c 16
#SBATCH --mem=240G
#SBATCH -t 2-00:00:00
#SBATCH --constraint=rocky8
#SBATCH --exclude=node4002,node3900
#SBATCH -o bench/runs/arms_logs/%x_%j.log
set -eu
S=$1
P=/orcd/pool/007/a_lin
cd $P/cadfit
module load apptainer/1.5.2 2>/dev/null || export PATH=/orcd/software/core/001/pkg/apptainer/1.5.2/bin:$PATH
apptainer exec -B /orcd $P/envs/cadfit-sandbox $P/envs/cadfit-venv/bin/python bench/trim_common_replay.py \
  bench/runs/h2s${S}_v3_trim.json --stl-dir bench/cadbench/fresh2 --jobs ${JOBS:-4} --out bench/runs/h2s${S}_v3_trim_common.json

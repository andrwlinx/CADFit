#!/bin/bash
# Pipeline arms on one ORCD CPU node, in the CADFit container. Runs the parts of
# <stl_dir> whose index i satisfies i % NCHUNK == CHUNK (sorted by name), so a
# cohort spreads over several jobs; outputs land in the shared bench/runs/<tag>_<arm>.
# Resumable (finished parts are skipped by run_parallel_arms.sh).
#
#   sbatch --array=0-1 bench/arms_job.sh bench/cadbench/fresh2 h2 2 "d0 v2"
# RUNNER_SRC: tree whose bench/run_parallel_arms.sh (arm flags, environment) runs;
# held-out jobs point it at their frozen source (bench/h2_submit.sh), default the checkout.
# The code snapshot for each arm (bench/runs/<tag>_<arm>_code) must exist before
# submitting: run_parallel_arms.sh only creates it when missing, so freeze it first.
#SBATCH -p mit_normal
#SBATCH -c 48
#SBATCH --mem=180G
#SBATCH -t 12:00:00
#SBATCH -o bench/runs/arms_logs/%x_%A_%a.log
set -u
STLS=$1; TAG=$2; NCHUNK=$3; ARMS=$4
CHUNK=${SLURM_ARRAY_TASK_ID:-0}
P=/orcd/pool/007/a_lin
cd $P/cadfit
SUB=bench/runs/${TAG}_chunks/c${CHUNK}
mkdir -p $SUB
i=0
for f in $(ls $STLS/*.stl | sort); do
  [ $((i % NCHUNK)) -eq $CHUNK ] && ln -sf $(realpath $f) $SUB/
  i=$((i + 1))
done
echo "[$(date +%T)] chunk $CHUNK/$NCHUNK: $(ls $SUB | wc -l) parts, arms: $ARMS, $(hostname)"
module load apptainer/1.5.2 2>/dev/null || export PATH=/orcd/software/core/001/pkg/apptainer/1.5.2/bin:$PATH  # some preemptable nodes have no lmod
apptainer exec -B /orcd $P/envs/cadfit-sandbox bash -c \
  "export PATH=$P/envs/cadfit-venv/bin:\$PATH; JOBS=${JOBS:-6} SEED=${SEED:-0} MIN_FREE_GB=50 MAX_RUNS_GB=400 \
   PY=$P/envs/cadfit-venv/bin/python bash ${RUNNER_SRC:-.}/bench/run_parallel_arms.sh $SUB $TAG $ARMS"
echo "[$(date +%T)] done"

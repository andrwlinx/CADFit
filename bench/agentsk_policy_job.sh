#!/bin/bash
#SBATCH -p mit_normal
#SBATCH -c 16
#SBATCH --mem=120G
#SBATCH -t 06:00:00
#SBATCH -J agentsk_policy
#SBATCH -o bench/runs/agentsk_logs/%x_%j.log
# No-LLM skills policy (agent/scripted_skills_policy.py) on the 20 study parts, 5 at a time.
P=/orcd/pool/007/a_lin
cd $P/cadfit
module load apptainer/1.5.2
# 5 parts at a time on 16 cores: cap numeric-library threads per process (unset, each
# process started ~46 threads and the node ran at load ~98, starving the 30-min clock).
export OMP_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3 MKL_NUM_THREADS=3 NUMEXPR_NUM_THREADS=3
RUN="apptainer exec -B /orcd $P/envs/cadfit-sandbox $P/envs/cadfit-venv/bin/python"
$RUN -c "import cadquery, manifold3d, trimesh, scipy, shapely" && echo "imports warm"
$RUN -c "import sys; sys.path.insert(0, 'agent'); from scripted_skills_policy import study_parts; print('\n'.join(study_parts()))" \
  | xargs -P 5 -I{} $RUN agent/scripted_skills_policy.py --parts {} --out bench/runs/agentsk_policy
$RUN agent/scripted_skills_policy.py --out bench/runs/agentsk_policy   # summary over all 20 (cached)

#!/bin/bash
# CADFit++ v2 held-out evaluation on ORCD (run on the login node, from the
# cadfit checkout, after syncing code + bench/cadbench/fresh2 from the Mac):
#
#   rsync -a --exclude bench/runs --exclude .venv ~/CADFit/ orcd:/orcd/pool/007/a_lin/cadfit/
#   rsync -a ~/CADFit/bench/runs/dev2_d0_code/ orcd:/orcd/pool/007/a_lin/cadfit/bench/runs/h2_d0_code/
#   ssh orcd 'cd /orcd/pool/007/a_lin/cadfit && bash bench/v2_submit.sh'
#
# Pipeline arms (300 parts, 4 chunks): d0 = pre-v2 code (git e260397), dx = +exec-verify
# only, v2 = all fixes. Agents (20 prespecified fresh2 parts, study_parts seed 1):
# Gemma-4-31B and Qwen3.6-35B-A3B, skills toolset, tools v1 vs v2, 3 episodes each.
# Scripted policy: agent economy, tools v1 vs v2.
set -eu
mkdir -p bench/runs/arms_logs bench/runs/agentsk_logs
test -f bench/runs/h2_d0_code/run_pipeline.py || { echo "missing h2_d0_code snapshot"; exit 1; }
for arm in dx v2; do  # freeze the v2 code now (run_parallel_arms.sh only copies when missing)
  mkdir -p bench/runs/h2_${arm}_code
  [ -f bench/runs/h2_${arm}_code/run_pipeline.py ] || cp ./*.py bench/runs/h2_${arm}_code/
done
sbatch -J h2arms --array=0-3 bench/arms_job.sh bench/cadbench/fresh2 h2 4 "d0 dx v2"

for model in gemma4-31b qwen36-35b-a3b; do
  for rep in 0 1 2; do
    sbatch -J ag_${model}_v1_r$rep --gres=gpu:h100:1 bench/agentsk_job.sh $model \
      --stl-dir bench/cadbench/fresh2 --toolsets skills --tag h2ag_v1_r$rep
    sbatch -J ag_${model}_v2_r$rep --gres=gpu:h100:1 --export=ALL,CADFIT_AGENT_EXEC=1 bench/agentsk_job.sh $model \
      --stl-dir bench/cadbench/fresh2 --toolsets skills --tag h2ag_v2_r$rep
  done
done

for v in v1 v2; do
  E=$([ $v = v2 ] && echo 1 || echo 0)
  sbatch -J h2pol_$v -p mit_normal -c 16 --mem=64G -t 12:00:00 -o bench/runs/agentsk_logs/%x_%j.log \
    --export=ALL,CADFIT_AGENT_EXEC=$E --wrap "module load apptainer/1.5.2; apptainer exec -B /orcd \
    /orcd/pool/007/a_lin/envs/cadfit-sandbox /orcd/pool/007/a_lin/envs/cadfit-venv/bin/python \
    agent/scripted_skills_policy.py --stl-dir bench/cadbench/fresh2 --out bench/runs/h2pol_$v --agent-economy --reserve 20"
done
squeue -u $USER

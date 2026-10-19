#!/bin/bash
# CADFit++ v2 evaluation on ORCD (run on the login node, from the cadfit checkout,
# after syncing code + cohort from the Mac):
#
#   rsync -a --exclude bench/runs --exclude .venv ~/CADFit/ orcd:/orcd/pool/007/a_lin/cadfit/
#   ssh orcd 'cd /orcd/pool/007/a_lin/cadfit && COMMIT=<sha> TAG=h2 STLS=bench/cadbench/fresh2 bash bench/v2_submit.sh'
#
# Every job runs from a frozen full source tree (git archive of one commit, review
# round 1 finding 5): arms d0/dx/v2 from bench/runs/<TAG>_<arm>_code, agents, the
# scripted policy and scoring from bench/runs/<TAG>_src. bench/runs and
# bench/cadbench inside a frozen tree are links to the checkout's, so outputs land
# in the shared run folder.
#
# Pipeline arms (4 chunks): d0 = pre-v2 code (git e260397), dx = d0 + execution-verified
# delivery (revolve and geometry fixes off), v2 = all fixes.
# Agents (20 prespecified parts, study_parts seed 1), Gemma-4-31B and Qwen3.6-35B-A3B,
# 3 episodes per condition:
#   skills v1 (earlier tools + harness) vs skills v2 (tools v2 + harness v2): the v2
#     *package* (feedback, executed answer, deadline, nudges), not tools alone;
#   code v2 and codesec v2: the toolset attribution under the corrected tools.
# Scripted policy (agent economy): tools v1 and v2, same deadline rule as agents.
set -eu
COMMIT=${COMMIT:?set COMMIT to the evaluated commit}
TAG=${TAG:-h2}
STLS=${STLS:-bench/cadbench/fresh2}
D0=${D0:-e260397}
mkdir -p bench/runs/arms_logs bench/runs/agentsk_logs

freeze() {  # <commit> <dir>: full tree of <commit>, made once
  [ -f "$2/run_pipeline.py" ] && { echo "frozen: $2 ($(cat "$2/SOURCE.txt"))"; return; }
  mkdir -p "$2"
  git archive "$1" | tar -x -C "$2"
  rm -rf "$2/bench/runs" "$2/bench/cadbench"
  ln -s "$PWD/bench/runs" "$2/bench/runs"
  ln -s "$PWD/bench/cadbench" "$2/bench/cadbench"
  echo "git archive $(git rev-parse "$1")" > "$2/SOURCE.txt"
  echo "froze $1 -> $2"
}
freeze "$D0" bench/runs/${TAG}_d0_code
for d in ${TAG}_dx_code ${TAG}_v2_code ${TAG}_src; do freeze "$COMMIT" bench/runs/$d; done
SRC=$PWD/bench/runs/${TAG}_src
N=$(ls $STLS/*.stl | wc -l)
echo "cohort $STLS: $N parts"

sbatch -J ${TAG}arms --array=0-3 bench/arms_job.sh $STLS $TAG 4 "d0 dx v2"

for model in gemma4-31b qwen36-35b-a3b; do
  for rep in 0 1 2; do
    sbatch -J ag_${model}_v1_r$rep --gres=gpu:h100:1 --export=ALL,CADFIT_SRC=$SRC bench/agentsk_job.sh $model \
      --stl-dir $STLS --toolsets skills --tag ${TAG}ag_v1_r$rep
    for ts in skills code codesec; do
      sbatch -J ag_${model}_v2${ts}_r$rep --gres=gpu:h100:1 --export=ALL,CADFIT_SRC=$SRC,CADFIT_AGENT_EXEC=1 \
        bench/agentsk_job.sh $model --stl-dir $STLS --toolsets $ts --tag ${TAG}ag_v2_r$rep
    done
  done
done

for v in v1 v2; do
  E=$([ $v = v2 ] && echo 1 || echo 0)
  sbatch -J ${TAG}pol_$v -p mit_normal -c 16 --mem=64G -t 12:00:00 -o bench/runs/agentsk_logs/%x_%j.log \
    --export=ALL,CADFIT_AGENT_EXEC=$E --wrap "cd $SRC; module load apptainer/1.5.2; apptainer exec -B /orcd \
    /orcd/pool/007/a_lin/envs/cadfit-sandbox /orcd/pool/007/a_lin/envs/cadfit-venv/bin/python \
    agent/scripted_skills_policy.py --stl-dir $STLS --out bench/runs/${TAG}pol_$v --agent-economy --reserve 20"
done
squeue -u $USER

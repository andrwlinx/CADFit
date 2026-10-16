#!/bin/bash
# Overnight package (RESEARCH_REVIEW.md §5): fresh 60-part cohort, four arms
# from one code version, corrected judge with CAD replay, section control,
# gated agent study. Launch: setsid nohup bash bench/overnight.sh > bench/runs/overnight.log 2>&1 &
set -u
cd ~/cadfit
export JOBS=5 MIN_FREE_GB=4 MAX_RUNS_GB=40
S=bench/cadbench/fresh
echo "[$(date +%T)] phase 1: arm C (beam, candidate pools kept)"
bash bench/run_parallel_arms.sh $S fresh beamkh
echo "[$(date +%T)] phase 2: agent study (background) + arms A, B, D"
bash bench/agent_study.sh > bench/runs/agentfr_study.log 2>&1 &
STUDY=$!
bash bench/run_parallel_arms.sh $S fresh base rules beamsec
echo "[$(date +%T)] phase 3: scoring (mesh + CAD replay)"
.venv/bin/python bench/score.py --cad --jobs 30 --runs bench/runs/fresh_base bench/runs/fresh_rules \
  bench/runs/fresh_beamkh bench/runs/fresh_beamsec --stl-dir $S --out bench/runs/fresh_scores.json \
  > bench/runs/fresh_scores.log 2>&1
tail -8 bench/runs/fresh_scores.log
echo "[$(date +%T)] phase 4: section control"
.venv/bin/python bench/section_control.py --run bench/runs/fresh_beamkh --stl-dir $S \
  --scores bench/runs/fresh_scores.json --out bench/runs/fresh_section_control.json
wait $STUDY
echo "[$(date +%T)] phase 5: agent study scores"
tail -6 bench/runs/agentfr/agentfr1.log bench/runs/agentfr/agentfr2.log 2>/dev/null
echo "[$(date +%T)] overnight done"

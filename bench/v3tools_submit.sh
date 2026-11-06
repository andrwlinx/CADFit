#!/bin/bash
# Tools-v3 study (review-stage/TOOLS_V3_PROTOCOL.md) on ORCD: Claude Opus/Sonnet 5.5 x
# tools {v2 = f4435df, v3 = 92ab47a} x toolsets {code, skills} on the 40 fresh3 parts,
# three independent episodes (r0-r2). Each tools version runs from its own frozen tree.
# Run from the checkout root:   bash bench/v3tools_submit.sh
set -eu
V2=f4435df V3=92ab47a
mkdir -p bench/runs/agentsk_logs
freeze() {  # <commit> <dir>
  [ -f "$2/SOURCE.txt" ] && { echo "frozen: $2 ($(cat "$2/SOURCE.txt"))"; return; }
  mkdir -p "$2"
  git archive "$1" | tar -x -C "$2"
  rm -rf "$2/bench/runs" "$2/bench/cadbench"
  ln -s "$PWD/bench/runs" "$2/bench/runs"
  ln -s "$PWD/bench/cadbench" "$2/bench/cadbench"
  echo "git archive $(git rev-parse "$1")" > "$2/SOURCE.txt"
}
freeze $V2 bench/runs/tv_v2_src
freeze $V3 bench/runs/tv_v3_src
PARTS=$(python3 -c "import json; d=json.load(open('bench/cadbench/fresh3_parts.json'))['parts']; print(*sum(d.values(), []))")
[ "$(echo $PARTS | wc -w)" = 40 ] || { echo "expected 40 fresh3 parts"; exit 1; }
for f in $PARTS; do [ -f bench/cadbench/fresh3/$f.stl ] || { echo "missing bench/cadbench/fresh3/$f.stl"; exit 1; }; done
for rep in r0 r1 r2; do
  for m in opus55 sonnet55; do
    for v in v2 v3; do
      sbatch -J tv_${m}_${v}_$rep -p mit_preemptable,mit_normal -c 16 --mem=64G -t 12:00:00 --exclude=node4002 \
        --export=ALL,CADFIT_SRC=$PWD/bench/runs/tv_${v}_src bench/runs/tv_${v}_src/bench/claude_job.sh $m \
        --toolsets code skills --stl-dir bench/cadbench/fresh3 --parts $PARTS --tag tv_${v}_$rep --jobs 8
    done
  done
done
squeue -u $USER -o "%.10i %.24j %.8T %R" | grep tv_

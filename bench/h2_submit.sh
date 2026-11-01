#!/bin/bash
# Held-out pipeline evaluation (review-stage/HELDOUT_PROTOCOL.md): fresh2, 300 parts.
#
#   ssh orcd 'cd /orcd/pool/007/a_lin/cadfit && COMMIT=<sha> bash bench/h2_submit.sh'
#
# Freezes every arm's full source before submitting (d0 from e260397 + the
# infrastructure + seeding-control patches; dx/v2/v3 from COMMIT), then submits:
#   h2s0: d0 dx v2 v3 with SEED 0;  h2s1, h2s2: v2 v3 with SEED 1, 2.
# 12 chunks of 25 parts per run, JOBS=3; scoring, trim, section control and
# surface agreement are submitted after the runs finish (bench/runs/*.sh helpers).
set -eu
COMMIT=${COMMIT:?set COMMIT to the evaluated commit}
STLS=${STLS:-bench/cadbench/fresh2}
D0=${D0:-e260397}
D0_PATCHES="bench/d0_infra.patch bench/d0_seed.patch"
NCHUNK=12
EXCL="node[1700-1705,1708-1709,1800-1805]"  # preemptable nodes without /orcd/software
git diff --quiet HEAD -- . ':!bench/runs' || { echo "uncommitted changes"; exit 1; }
[ "$(git rev-parse HEAD)" = "$(git rev-parse "$COMMIT")" ] || { echo "checkout is not at COMMIT"; exit 1; }
mkdir -p bench/runs/arms_logs

freeze() {  # <commit> <dir>: full tree of <commit>, made once
  [ -f "$2/run_pipeline.py" ] && { echo "frozen: $2 ($(head -1 "$2/SOURCE.txt"))"; return; }
  mkdir -p "$2"
  git archive "$1" | tar -x -C "$2"
  rm -rf "$2/bench/runs" "$2/bench/cadbench"
  ln -s "$PWD/bench/runs" "$2/bench/runs"
  ln -s "$PWD/bench/cadbench" "$2/bench/cadbench"
  echo "git archive $(git rev-parse "$1")" > "$2/SOURCE.txt"
  echo "froze $1 -> $2"
}

freeze "$D0" bench/runs/h2s0_d0_code
# d0 gets the common infrastructure fix (decimation memory bound, CadQuery worker
# retry) and the common experimental control (revolve-axis surface sampling seeded
# by CADFIT_SEED, as every other analysis stage and arm): no method change.
grep -q patches bench/runs/h2s0_d0_code/SOURCE.txt || {
  for pt in $D0_PATCHES; do git apply --directory=bench/runs/h2s0_d0_code "$pt"; done
  echo "+ patches: $D0_PATCHES" >> bench/runs/h2s0_d0_code/SOURCE.txt
}
freeze "$COMMIT" bench/runs/h2s0_dx_code
for s in 0 1 2; do for a in v2 v3; do freeze "$COMMIT" bench/runs/h2s${s}_${a}_code; done; done
freeze "$COMMIT" bench/runs/h2_src  # scoring / trim / section control / surface agreement

echo "cohort $STLS: $(ls $STLS/*.stl | wc -l) parts"
A="-p mit_normal,mit_preemptable --requeue --exclude=$EXCL -t 12:00:00 --array=0-$((NCHUNK - 1))"
# The runner (arm flags, environment) also comes from the frozen tree, not the checkout.
export RUNNER_SRC=bench/runs/h2_src
SEED=0 JOBS=3 sbatch -J h2s0 $A bench/arms_job.sh $STLS h2s0 $NCHUNK "d0 dx v2 v3"
for s in 1 2; do SEED=$s JOBS=3 sbatch -J h2s$s $A bench/arms_job.sh $STLS h2s$s $NCHUNK "v2 v3"; done
squeue -u $USER

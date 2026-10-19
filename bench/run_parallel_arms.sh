#!/bin/bash
# Parallel version of run_full_arms.sh for a big Linux box: same arms, flags,
# frozen code snapshot and per-part outputs, but JOBS parts at a time.
#
# Usage: JOBS=7 bench/run_parallel_arms.sh <stl_dir> <tag> [arm ...]
# Env:   JOBS         parts run at once (default 7)
#        MIN_FREE_GB  stop launching parts below this much free disk (default 80)
#        MAX_RUNS_GB  stop launching parts once bench/runs exceeds this (default 60)
# Each part's pipeline gets ~nproc/JOBS inner workers (CADFIT_MAX_PARALLEL).
# Score: .venv/bin/python bench/score.py --jobs 40 --runs bench/runs/<tag>_* --stl-dir <stl_dir>
set -u
STLS=$1; TAG=$2; shift 2
ARMS=${@:-base speed}
JOBS=${JOBS:-7}
MIN_FREE_GB=${MIN_FREE_GB:-80}
MAX_RUNS_GB=${MAX_RUNS_GB:-60}
PY=${PY:-.venv/bin/python}
COMMON="--max-iterations 1 --seed 0"
export CADFIT_MAX_PARALLEL=$JOBS
# A part killed mid-run (timeout, OOM) otherwise loses its block-buffered log:
# abc60r beam/00000914 exited after 6 min with an empty log and no outputs.
export PYTHONUNBUFFERED=1

flags_for() {
  case $1 in
    stock)   echo "--no-fix-sketch-identity --no-fix-iou-validity --no-cache-volumes --no-persistent-pool --no-cache-solids --no-fast-cd --no-guard-refine --no-fix-slice-fallback --max-slice-loops 0" ;;
    base)    echo "" ;;
    speed)   echo "--persistent-cq --exact-union" ;;
    cut)     echo "--persistent-cq --exact-union --cut-phase" ;;
    rules)   echo "--persistent-cq --exact-union --cut-phase --event-slices --detect-directions --translation-max-points 400" ;;
    all)     echo "--persistent-cq --exact-union --cut-phase --event-slices --detect-directions --translation-max-points 400 --sweep-loft --emit-splines" ;;
    ms)      echo "--persistent-cq --exact-union --cut-phase --event-slices --detect-directions --translation-max-points 400 --sweep-loft --emit-splines --multistart" ;;
    beam)    echo "--persistent-cq --exact-union --cut-phase --event-slices --detect-directions --translation-max-points 400 --beam 4" ;;
    beamkh)  echo "--persistent-cq --exact-union --cut-phase --event-slices --detect-directions --translation-max-points 400 --beam 4 --keep-history" ;;
    beamsec) echo "--persistent-cq --exact-union --cut-phase --event-slices --detect-directions --translation-max-points 400 --beam 4 --section-extrude" ;;
    # CADFit++ v2 (2026-10-18). d0 = beamsec flags run from the pre-v2 code snapshot
    # (bench/runs/<tag>_d0_code from git e260397); dx = + execution-verified delivery
    # only; v2 = + original-mesh sections/scoring + shared geometry fixes.
    d0)      echo "--persistent-cq --exact-union --cut-phase --event-slices --detect-directions --translation-max-points 400 --beam 4 --section-extrude" ;;
    dx)      echo "--persistent-cq --exact-union --cut-phase --event-slices --detect-directions --translation-max-points 400 --beam 4 --section-extrude --exec-verify" ;;
    v2)      echo "--persistent-cq --exact-union --cut-phase --event-slices --detect-directions --translation-max-points 400 --beam 4 --section-extrude --exec-verify --section-original --score-original --shared-fixes" ;;
    basegwn) echo "--gwn-repair" ;;
    beamgwn) echo "--persistent-cq --exact-union --cut-phase --event-slices --detect-directions --translation-max-points 400 --beam 4 --gwn-repair" ;;
    *) return 1 ;;
  esac
}

# Disk guard, checked before each part starts (portable df: 1K blocks).
disk_ok() {
  local free_gb runs_gb
  free_gb=$(( $(df -Pk . | awk 'NR==2 {print $4}') / 1048576 ))
  runs_gb=$(( $(du -sk bench/runs | cut -f1) / 1048576 ))
  if [ "$free_gb" -lt "$MIN_FREE_GB" ] || [ "$runs_gb" -gt "$MAX_RUNS_GB" ]; then
    echo "[$(date +%T)] disk guard: ${free_gb} GB free, bench/runs ${runs_gb} GB; not starting $1"
    return 1
  fi
}

run_part() {  # <arm> <part>
  local arm=$1 part=$2 OUT=bench/runs/${TAG}_$1
  [ -f "$OUT/$part/final_iou.json" ] && return 0
  disk_ok "$arm/$part" || return 1
  echo "[$(date +%T)] start $arm/$part"
  # dx isolates execution-verified delivery: stock revolve axes (no origin fix).
  if [ "$arm" = dx ]; then export CADFIT_FIX_REVOLVE_ORIGIN=0; else unset CADFIT_FIX_REVOLVE_ORIGIN; fi
  # Per-part log: concurrent parts would interleave in one file.
  mkdir -p "$OUT/logs"
  CADFIT_PROFILE="$OUT/profile.jsonl" $PY "bench/runs/${TAG}_${arm}_code/run_pipeline.py" \
    "bench/runs/${TAG}_${arm}_in" --output-folder "$OUT" --start-from "$part.stl" --limit 1 \
    $COMMON $(flags_for "$arm") > "$OUT/logs/$part.txt" 2>&1
  local rc=$?
  # --keep-history arms: keep only what the agent's workspace reads (candidate
  # STL/scripts, their metadata, the final model); history is ~1 GB a part.
  if [ "$arm" = beamkh ] && [ -d "$OUT/$part" ]; then
    find "$OUT/$part" -mindepth 1 -maxdepth 1 ! -name 'sketch_*.stl' ! -name 'sketch_*.py' \
      ! -name 'generic_*.stl' ! -name 'generic_*.py' ! -name 'evaluated_operations.json' \
      ! -name 'best_greedy_parallel*' ! -name 'final_iou.json' ! -name 'greedy_final_iou.json' \
      -exec rm -rf {} +
  fi
  echo "[$(date +%T)] done  $arm/$part exit $rc"
}
export -f run_part disk_ok flags_for
export TAG PY COMMON MIN_FREE_GB MAX_RUNS_GB

for arm in $ARMS; do
  flags_for "$arm" > /dev/null || { echo "unknown arm $arm"; exit 1; }
  OUT=bench/runs/${TAG}_${arm}; IN=bench/runs/${TAG}_${arm}_in; CODE=bench/runs/${TAG}_${arm}_code
  mkdir -p "$OUT" "$IN" "$CODE"
  cp -n "$STLS"/*.stl "$IN"/
  [ -d "$STLS/.gwn" ] && mkdir -p "$IN/.gwn" && cp -n "$STLS"/.gwn/*.stl "$IN/.gwn/" 2>/dev/null
  [ -f "$CODE/run_pipeline.py" ] || cp ./*.py "$CODE"/
  git rev-parse HEAD > "$CODE/GIT_HEAD" 2>/dev/null; git diff > "$CODE/GIT_DIFF.patch" 2>/dev/null
  echo "[$(date +%T)] arm=$arm flags: $(flags_for "$arm") jobs=$JOBS"
done

# One queue, part-major (every arm of a part before the next part) so a run cut
# short still leaves paired results; largest STL first so stragglers start early.
for stl in $(ls -S "$STLS"/*.stl); do
  for arm in $ARMS; do echo "$arm $(basename "$stl" .stl)"; done
done | xargs -P "$JOBS" -L 1 bash -c 'run_part "$0" "$1"'
echo "[$(date +%T)] all arms done"

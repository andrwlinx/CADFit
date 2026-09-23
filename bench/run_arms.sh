#!/bin/bash
# Re-run only greedy_search.py (pipeline step 7) for several arms on top of the
# cached analysis outputs of a kept-history stock run. The analysis stage is
# unseeded, so reusing it removes that noise from the comparison.
#
# Usage: bench/run_arms.sh <stock_runs_dir> <stl_dir> <out_dir> [arm ...]
#   arms: stock fast rank1 rank2 rank1drop full identity iouv fixed fixed_vol fixed_pool fixed_solids fixed_all
set -u
STOCK=$1; STLS=$2; OUT=$3; shift 3
ARMS=${@:-stock fixed fixed_all}
PY=.venv/bin/python
WORKERS=${CADFIT_INNER_WORKERS:-6}

OFF_FIX="--no-fix-sketch-identity --no-fix-iou-validity"
OFF_CACHE="--no-cache-volumes --no-persistent-pool --no-cache-solids"
for arm in $ARMS; do
  case $arm in
    stock)     FLAGS="$OFF_FIX $OFF_CACHE" ;;
    fast)      FLAGS="$OFF_FIX --no-cache-solids" ;;
    rank1)     FLAGS="$OFF_FIX $OFF_CACHE --candidate-ranking --candidate-per-group 1" ;;
    rank2)     FLAGS="$OFF_FIX $OFF_CACHE --candidate-ranking --candidate-per-group 2" ;;
    rank1drop) FLAGS="$OFF_FIX $OFF_CACHE --candidate-ranking --candidate-per-group 1 --candidate-drop-tau 0.002" ;;
    full)      FLAGS="$OFF_FIX --no-cache-solids --candidate-ranking --candidate-per-group 1 --candidate-drop-tau 0.002" ;;
    identity)  FLAGS="--no-fix-iou-validity $OFF_CACHE" ;;
    iouv)      FLAGS="--no-fix-sketch-identity $OFF_CACHE" ;;
    fixed)     FLAGS="$OFF_CACHE" ;;
    fixed_vol) FLAGS="--no-persistent-pool --no-cache-solids" ;;
    fixed_pool) FLAGS="--no-cache-volumes --no-cache-solids" ;;
    fixed_solids) FLAGS="--no-cache-volumes --no-persistent-pool" ;;
    fixed_all) FLAGS="" ;;
    *) echo "unknown arm $arm"; exit 1 ;;
  esac
  for run in "$STOCK"/*/; do
    id=$(basename "$run")
    [ -f "$run/loops_split.json" ] || continue
    [ -f "$STLS/$id.stl" ] || continue
    dst="$OUT/$arm/$id"
    [ -f "$dst/done" ] && continue
    rm -rf "$dst"; mkdir -p "$dst"
    start=$(date +%s)
    CADFIT_PROFILE="$dst/profile.jsonl" PYTHONPATH=. caffeinate -dims $PY greedy_search.py \
      "$run/loops_split.json" "$run/loops_split_revolve.json" "$STLS/$id.stl" \
      "$run/translation_analysis" "$run/revolve_analysis" \
      --output-folder "$dst" --num-workers "$WORKERS" --normalize $FLAGS > "$dst/log.txt" 2>&1
    rc=$?
    echo "{\"arm\": \"$arm\", \"id\": \"$id\", \"wall\": $(( $(date +%s) - start )), \"exit\": $rc}" > "$dst/done"
    echo "$arm $id $(cat "$dst/done")"
  done
done

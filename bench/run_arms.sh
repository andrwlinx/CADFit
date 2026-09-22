#!/bin/bash
# Re-run only greedy_search.py (pipeline step 7) for several arms on top of the
# cached analysis outputs of a kept-history stock run. The analysis stage is
# unseeded, so reusing it removes that noise from the comparison.
#
# Usage: bench/run_arms.sh <stock_runs_dir> <stl_dir> <out_dir> [arm ...]
#   arms: stock fast rank1 rank2 rank1drop full   (default: all)
set -u
STOCK=$1; STLS=$2; OUT=$3; shift 3
ARMS=${@:-stock fast rank1 rank2 rank1drop full}
PY=.venv/bin/python
WORKERS=${CADFIT_INNER_WORKERS:-6}

for arm in $ARMS; do
  case $arm in
    stock)     FLAGS="" ;;
    fast)      FLAGS="--fast-prune" ;;
    rank1)     FLAGS="--candidate-ranking --candidate-per-group 1" ;;
    rank2)     FLAGS="--candidate-ranking --candidate-per-group 2" ;;
    rank1drop) FLAGS="--candidate-ranking --candidate-per-group 1 --candidate-drop-tau 0.002" ;;
    full)      FLAGS="--fast-prune --candidate-ranking --candidate-per-group 1 --candidate-drop-tau 0.002" ;;
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
    CADFIT_PROFILE="$dst/profile.jsonl" PYTHONPATH=. $PY greedy_search.py \
      "$run/loops_split.json" "$run/loops_split_revolve.json" "$STLS/$id.stl" \
      "$run/translation_analysis" "$run/revolve_analysis" \
      --output-folder "$dst" --num-workers "$WORKERS" --normalize $FLAGS > "$dst/log.txt" 2>&1
    rc=$?
    echo "{\"arm\": \"$arm\", \"id\": \"$id\", \"wall\": $(( $(date +%s) - start )), \"exit\": $rc}" > "$dst/done"
    echo "$arm $id $(cat "$dst/done")"
  done
done

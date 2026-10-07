#!/bin/bash
# Full-pipeline arms (analysis + greedy + refinement) on a folder of STLs.
# Inputs are copied per arm because run_pipeline.py repairs non-watertight
# STLs in place. Analysis is seeded, so arms differ only by their flags.
#
# Usage: bench/run_full_arms.sh <stl_dir> <tag> [arm ...]
#   arms: stock base speed cut rules all ms beam basegwn beamgwn
# Outputs: bench/runs/<tag>_<arm>/{<part>/..., profile.jsonl, log.txt}
# Score:   .venv/bin/python bench/score.py --runs bench/runs/<tag>_* --stl-dir <stl_dir>
set -u
STLS=$1; TAG=$2; shift 2
ARMS=${@:-base speed}
PY=.venv/bin/python
COMMON="--max-iterations 1 --seed 0"

free_gb() { df -g . | awk 'NR==2 {print $4}'; }
for arm in $ARMS; do
  if [ "$(free_gb)" -lt 3 ]; then echo "[$(date +%T)] stopping: less than 3 GB free"; exit 1; fi
  case $arm in
    stock)   FLAGS="--no-fix-sketch-identity --no-fix-iou-validity --no-cache-volumes --no-persistent-pool --no-cache-solids --no-fast-cd --no-guard-refine --no-fix-slice-fallback --max-slice-loops 0" ;;
    base)    FLAGS="" ;;
    speed)   FLAGS="--persistent-cq --exact-union" ;;
    cut)     FLAGS="--persistent-cq --exact-union --cut-phase" ;;
    rules)   FLAGS="--persistent-cq --exact-union --cut-phase --event-slices --detect-directions --translation-max-points 400" ;;
    all)     FLAGS="--persistent-cq --exact-union --cut-phase --event-slices --detect-directions --translation-max-points 400 --sweep-loft --emit-splines" ;;
    ms)      FLAGS="--persistent-cq --exact-union --cut-phase --event-slices --detect-directions --translation-max-points 400 --sweep-loft --emit-splines --multistart" ;;
    beam)    FLAGS="--persistent-cq --exact-union --cut-phase --event-slices --detect-directions --translation-max-points 400 --beam 4" ;;
    basegwn) FLAGS="--gwn-repair" ;;
    beamgwn) FLAGS="--persistent-cq --exact-union --cut-phase --event-slices --detect-directions --translation-max-points 400 --beam 4 --gwn-repair" ;;
    *) echo "unknown arm $arm"; exit 1 ;;
  esac
  OUT=bench/runs/${TAG}_${arm}
  IN=bench/runs/${TAG}_${arm}_in
  CODE=bench/runs/${TAG}_${arm}_code
  mkdir -p "$OUT" "$IN" "$CODE"
  cp -n "$STLS"/*.stl "$IN"/
  # Run from a frozen copy of the code so edits during a long run cannot leak in
  # (run_pipeline.py resolves every sibling script relative to its own path).
  [ -f "$CODE/run_pipeline.py" ] || cp ./*.py "$CODE"/
  git rev-parse HEAD > "$CODE/GIT_HEAD"; git diff > "$CODE/GIT_DIFF.patch"
  echo "[$(date +%T)] arm=$arm flags: $FLAGS"
  # $FLAGS is intentionally unquoted: word-split into separate flags (bash, not zsh).
  # One part per pipeline invocation so the disk guard runs between parts;
  # each part is attempted once (a crash leaves no final_iou.json and is
  # reported by bench/score.py as invalid).
  for stl in "$IN"/*.stl; do
    part=$(basename "$stl" .stl)
    [ -f "$OUT/$part/final_iou.json" ] && continue
    if [ "$(free_gb)" -lt 3 ]; then echo "[$(date +%T)] stopping: less than 3 GB free"; exit 1; fi
    CADFIT_PROFILE="$OUT/profile.jsonl" caffeinate -dims $PY "$CODE/run_pipeline.py" "$IN" \
      --output-folder "$OUT" --start-from "$part.stl" --limit 1 $COMMON $FLAGS >> "$OUT/log.txt" 2>&1
  done
  echo "[$(date +%T)] arm=$arm done"
done

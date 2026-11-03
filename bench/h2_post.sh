#!/bin/bash
#SBATCH -p mit_normal
#SBATCH -c 32
#SBATCH --mem=240G
#SBATCH -t 12:00:00
#SBATCH -o bench/runs/arms_logs/h2post_%x_%j.log
# Held-out post-processing (review-stage/HELDOUT_PROTOCOL.md), every step run from the
# frozen tree bench/runs/h2_src (its bench/runs and bench/cadbench link to the shared ones).
# Submit from the checkout root, in this order (each step after the previous one finished):
#
#   sbatch -J score   bench/h2_post.sh score          (or: per run `score1 <run>`, then `merge`)
#   for s in 0 1 2; do sbatch -J trim$s bench/h2_post.sh trim h2s${s}_v3; done
#   sbatch -J section bench/h2_post.sh section
#   sbatch -J rejudge bench/h2_post.sh rejudge
#   sbatch -J surface bench/h2_post.sh surface
#   sbatch -J timing  bench/h2_post.sh timing
#   sbatch -J stats   bench/h2_post.sh stats
set -eu
STEP=$1; shift || true
P=/orcd/pool/007/a_lin
module load apptainer/1.5.2 2>/dev/null || export PATH=/orcd/software/core/001/pkg/apptainer/1.5.2/bin:$PATH
# POST_SRC: the frozen tree to run from (default h2_src = git archive of the launch commit;
# h2_src_c = the same plus score.py's per-part result cache, an I/O-only amendment).
cd $P/cadfit/bench/runs/${POST_SRC:-h2_src}
PY="apptainer exec -B /orcd $P/envs/cadfit-sandbox $P/envs/cadfit-venv/bin/python"
STLS=bench/cadbench/fresh2
MAN=$STLS/manifest.json
R=bench/runs
RUNS="h2s0_d0 h2s0_dx h2s0_v2 h2s0_v3 h2s1_v2 h2s1_v3 h2s2_v2 h2s2_v3"
TRIMS="h2s0_v3trim=$R/h2s0_v3_trim.json h2s1_v3trim=$R/h2s1_v3_trim.json h2s2_v3trim=$R/h2s2_v3_trim.json"
case $STEP in
  score)    # primary metric for every arm-run: replay, OCC validity, robust judge
    $PY bench/score.py --runs $(for r in $RUNS; do echo -n "$R/$r "; done) --stl-dir $STLS --cad --jobs 8 \
      --out $R/h2_scores.json ;;
  score1)   # the same scoring for one run (one job per run fits the 12 h limit; then `merge`)
    $PY bench/score.py --runs $R/$1 --stl-dir $STLS --cad --jobs 12 --out $R/h2_scores_$1.json ;;
  merge)    # h2_scores.json from the per-run files, refusing any run that is missing
    $PY -c "
import json, sys
out = {}
for r in '$RUNS'.split():
    out.update(json.load(open('$R/h2_scores_' + r + '.json')))
missing = [r for r in '$RUNS'.split() if r not in out]
sys.exit('missing runs: ' + ' '.join(missing)) if missing else json.dump(out, open('$R/h2_scores.json', 'w'))
print('merged', len(out), 'runs')" ;;
  trim)     # final method: v3 delivery + silhouette-trim variant, selected by exec-verify
    $PY bench/analysis/trim_posthoc.py $R/$1 $STLS --jobs 8 --out $R/$1_trim.json ;;
  section)  # executed section-only reference (deterministic)
    $PY bench/section_control.py --run $R/h2s0_v2 --stl-dir $STLS --scores $R/h2_scores.json \
      --out $R/h2_section_control.json --jobs 16 ;;
  rejudge)  # independent seed, 4x samples, on the delivered artifacts (selection fixed)
    $PY bench/rejudge.py --stl-dir $STLS --manifest $MAN --scores $R/h2_scores.json --runs $RUNS \
      --trim $TRIMS --jobs 16 --out $R/h2_rejudge.json ;;
  surface)  # diagnostic surface agreement, fused occupied boundary, selected trim artifacts
    $PY bench/detail_scores.py --runs $RUNS --scores $R/h2_scores.json --trim $TRIMS --stl-dir $STLS \
      --jobs 4 --out $R/h2_detail.json ;;
  timing)   # successful-attempt latency per run and part, attempts, concurrency, trim stage
    $PY bench/analysis/timing_export.py --manifest $MAN --runs $RUNS --logs "$R/arms_logs/h2s*_*.log" \
      --trim h2s0_v3=$R/h2s0_v3_trim.json h2s1_v3=$R/h2s1_v3_trim.json h2s2_v3=$R/h2s2_v3_trim.json \
      --out $R/h2_timing.json ;;
  stats)    # primary contrast alone; secondary family (Holm over these 4 sign tests): v2-dx, v3-v2,
            # trim-v3, trim-section; repeats averaged within part. Then the same on the re-judged values.
    AVG="v2x3=h2s0_v2,h2s1_v2,h2s2_v2 v3x3=h2s0_v3,h2s1_v3,h2s2_v3 trimx3=h2s0_v3trim,h2s1_v3trim,h2s2_v3trim"
    $PY bench/analysis/v2_dev.py $R/h2_scores.json --manifest $MAN --pairs h2s0_dx:h2s0_d0 --out $R/h2_primary.json
    $PY bench/analysis/v2_dev.py $R/h2_scores.json --manifest $MAN --trim $TRIMS --section section=$R/h2_section_control.json \
      --avg $AVG --pairs v2x3:h2s0_dx v3x3:v2x3 trimx3:v3x3 trimx3:section --out $R/h2_secondary.json
    $PY bench/analysis/v2_dev.py $R/h2_rejudge.json --manifest $MAN --pairs h2s0_dx:h2s0_d0 --out $R/h2_primary_rejudged.json
    $PY bench/analysis/v2_dev.py $R/h2_rejudge.json --manifest $MAN --section section=$R/h2_section_control.json \
      --avg $AVG --pairs v2x3:h2s0_dx v3x3:v2x3 trimx3:v3x3 trimx3:section --out $R/h2_secondary_rejudged.json ;;
  *) echo "unknown step $STEP"; exit 1 ;;
esac

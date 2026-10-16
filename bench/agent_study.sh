#!/bin/bash
# Gated agent study on the fresh cohort (RESEARCH_REVIEW.md §5 step 4).
# Needs: arm beamkh finished (bench/runs/fresh_beamkh, pruned candidate pools)
# and the Qwen3.8 vLLM server on 127.0.0.1:8000 (see bench/runs/agentq38b.sh).
# Gate (fixed before any agent outcome): beam pipeline judge IoU < 0.90;
# at most 20 eligible parts, sampled with seed 0. Conditions, same starting model:
#   pipeline (as is) | search (equal-time scripted search, agent/search_baseline.py)
#   | Qwen3.8 refine, 2 repeats (agentfr1, agentfr2), 40 calls / enforced 20 min.
set -u
cd ~/cadfit
PREP=bench/runs/fresh_beamkh; STL=bench/cadbench/fresh; OUT=bench/runs/agentfr
mkdir -p $OUT
.venv/bin/python bench/score.py --jobs 20 --runs $PREP --stl-dir $STL --out $OUT/gate_scores.json > $OUT/gate_scores.log 2>&1
.venv/bin/python - <<'PY' > $OUT/parts.txt
import json, random
s = json.load(open('bench/runs/agentfr/gate_scores.json'))['fresh_beamkh']
elig = sorted(p for p, r in s.items() if r and r['valid'] and r['iou'] < 0.90)
pick = sorted(random.Random(0).sample(elig, min(20, len(elig))))
json.dump({'n_parts': len(s), 'eligible': elig, 'picked': pick},
          open('bench/runs/agentfr/gate.json', 'w'), indent=1)
print('\n'.join(pick))
PY
echo "[$(date +%T)] gate: $(wc -l < $OUT/parts.txt) parts picked"
# An empty --parts makes run_agent_bench.py fall back to every part (ungated).
[ -s $OUT/parts.txt ] || { echo "gate produced no parts; see $OUT/gate_scores.log"; exit 1; }
# No-op control: load the pipeline model into the workspace and export it
# untouched (the exporter alone changed 00479221's judge score: MC -> exact).
for p in $(cat $OUT/parts.txt); do
  o=bench/runs/agentfr1/noop/refine/$p; [ -f $o/result.json ] && continue; mkdir -p $o
  .venv/bin/python agent/search_baseline.py --gt $STL/$p.stl --cands $PREP/$p \
    --init $PREP/$p/best_greedy_parallel_iterative.py --out $o --max-minutes 0 > $o/stdout.txt 2>&1
done
# Equal-time scripted search, 5 at a time (CPU).
cat $OUT/parts.txt | xargs -P 5 -I{} sh -c '
  o=bench/runs/agentfr1/search/refine/{}; [ -f $o/result.json ] && exit 0; mkdir -p $o
  .venv/bin/python agent/search_baseline.py --gt bench/cadbench/fresh/{}.stl --cands bench/runs/fresh_beamkh/{} \
    --init bench/runs/fresh_beamkh/{}/best_greedy_parallel_iterative.py --out $o --max-minutes 20 > $o/stdout.txt 2>&1' &
# Two agent repeats at once (the server takes 2 sequences).
for t in agentfr1 agentfr2; do
  AGENT_API_KEY=local .venv/bin/python -u agent/run_agent_bench.py --prep $PREP --stl-dir $STL \
    --models RedHatAI/Qwen3.8-27B-INT4 --modes refine --tag $t --parts $(cat $OUT/parts.txt) \
    --base-url http://127.0.0.1:8000/v1 --keep-tool-results 6 --max-tokens 16384 --temperature 1.0 \
    --extra-body '{"top_p": 0.95, "top_k": 20, "chat_template_kwargs": {"enable_thinking": true}}' \
    > $OUT/$t.log 2>&1 &
done
wait
echo "[$(date +%T)] agent study done"

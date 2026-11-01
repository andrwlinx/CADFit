#!/usr/bin/env python3
"""
The fresh2 parts reserved for the GPU studies (LLM agents, CADFather), drawn from the
manifest alone before any fresh2 outcome exists: 20 benchA + 20 benchE parts,
random.Random(20261101).sample over each split's file_ids in sorted order.

  python3 bench/fresh2_subset.py   # -> bench/cadbench/fresh2_subset.json
"""
import json
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
man = json.load(open(os.path.join(ROOT, 'bench', 'cadbench', 'fresh2', 'manifest.json')))
r = random.Random(20261101)
subset = {}
for split in ('benchA', 'benchE'):
    ids = sorted(m['file_id'] for m in man if m['split'] == split)
    subset[split] = sorted(r.sample(ids, 20))
out = os.path.join(ROOT, 'bench', 'cadbench', 'fresh2_subset.json')
json.dump({'rule': __doc__.strip(), 'parts': subset}, open(out, 'w'), indent=1)
print(out, {k: len(v) for k, v in subset.items()})

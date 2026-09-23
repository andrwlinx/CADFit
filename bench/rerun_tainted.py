#!/usr/bin/env python3
"""Delete the output of tainted (arm, part) runs so bench/run_arms.sh redoes them.
Usage: python bench/rerun_tainted.py <arms_dir> [arm ...]"""
import json, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from compare import load_run
arms_dir = sys.argv[1]; only = set(sys.argv[2:])
runs = {}
for arm in sorted(os.listdir(arms_dir)):
    for part in sorted(os.listdir(os.path.join(arms_dir, arm))):
        folder = os.path.join(arms_dir, arm, part)
        if os.path.exists(os.path.join(folder, 'done')):
            runs.setdefault(arm, {})[part] = load_run(folder)
for part in {p for d in runs.values() for p in d}:
    med = float(np.median([runs[a][part].get('outside_span', 0.0) for a in runs if part in runs[a]]))
    for a in runs:
        if part in runs[a] and runs[a][part].get('outside_span', 0.0) > max(15.0, 2.5 * med):
            runs[a][part]['tainted'] = True
for arm in sorted(runs):
    if only and arm not in only: continue
    for part, r in sorted(runs[arm].items()):
        folder = os.path.join(arms_dir, arm, part)
        if r['tainted']:
            print(f"rerun {arm}/{part}: wall={r['wall']} max_gap={r['max_gap']:.0f} outside={r.get('outside_span', 0):.0f}")
            shutil.rmtree(folder)

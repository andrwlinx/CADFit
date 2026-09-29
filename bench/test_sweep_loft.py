#!/usr/bin/env python3
"""
Recovery test for analyze_sweep_loft.py on the phase-3 synthetic parts.

For each part: extract sketches exactly as the pipeline does (planar contours +
axis slices, split, combined), propose sweep/loft candidates, build each one
and report the best single-candidate IoU per kind against the ground truth.

Usage: python bench/test_sweep_loft.py [bench/synthetic_p3] [--work DIR]
"""
import argparse
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from cadquery_ops import execute_cadquery_script, compute_iou, generate_generic_script  # noqa: E402

PY = sys.executable


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=ROOT)


def seeds(stl, work):
    pc, ps = f'{work}/planar_contours.json', f'{work}/planar_loops_split.json'
    ax, axs = f'{work}/axis_sketches.json', f'{work}/axis_loops_split.json'
    run([PY, 'extract_planar_contours.py', stl, '--out', pc, '--delta', '0.05', '--normalize', '--num-workers', '6'])
    run([PY, 'split_loops.py', pc, '--group-contained', '--out', ps])
    run([PY, 'extract_sketches.py', stl, '--out', ax, '--axis-slices', '5', '--normalize'])
    run([PY, 'split_loops.py', ax, '--group-contained', '--out', axs])
    loops = json.load(open(ps)) + json.load(open(axs))
    out = f'{work}/loops_split.json'
    json.dump(loops, open(out, 'w'))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('folder', nargs='?', default='bench/synthetic_p3')
    ap.add_argument('--work', default='bench/runs/test_sweep_loft')
    args = ap.parse_args()
    summary = {}
    for stl in sorted(glob.glob(os.path.join(args.folder, '*.stl'))):
        name = os.path.splitext(os.path.basename(stl))[0]
        work = os.path.abspath(os.path.join(args.work, name))
        os.makedirs(work, exist_ok=True)
        loops = seeds(os.path.abspath(stl), work)
        cj = f'{work}/sweep_loft_candidates.json'
        run([PY, 'analyze_sweep_loft.py', loops, os.path.abspath(stl), '--out', cj, '--normalize'])
        cands = json.load(open(cj))
        best = {}
        for i, c in enumerate(cands):
            out = f'{work}/cand_{i}.stl'
            if not execute_cadquery_script(generate_generic_script(c['code'], out), out, f'{work}/cand_{i}.py'):
                continue
            v = compute_iou(os.path.abspath(stl), out, normalize=True)
            tag = c['kind'] + ('_bent' if c.get('bent') else '') + (f"_frenet{c['frenet']}" if 'frenet' in c else '')
            if v > best.get(tag, (0, None))[0]:
                best[tag] = (v, i)
        summary[name] = {k: round(v[0], 4) for k, v in best.items()}
        summary[name]['n_cands'] = len(cands)
        print('RESULT', name, summary[name], file=sys.stderr, flush=True)
    json.dump(summary, open(os.path.join(args.work, 'summary.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()

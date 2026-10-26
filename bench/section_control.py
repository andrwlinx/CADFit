#!/usr/bin/env python3
"""
Standalone section-extrusion control (RESEARCH_REVIEW.md §4).

For each part of a pipeline run: build the three section extrusions of the
target (section_extrude.py), score each against the target, and report

  pipeline        the run's own reconstruction
  sections        the best of the three section extrusions alone
  best_of         the better of the pipeline and the best section extrusion

Selection uses IoU against the input target, which every method sees (on
CADBench the input mesh is the ground truth, so selection and judge coincide;
this is the same information the pipeline's greedy search optimizes).

  python bench/section_control.py --run bench/runs/fresh_beamkh --stl-dir bench/cadbench/fresh \
      --scores bench/runs/fresh_scores.json --out bench/runs/fresh_section_control.json
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)


def one(job):
    part, gt, outdir = job
    import trimesh
    import iou
    import score
    import section_extrude as se
    from cadquery_ops import generate_generic_script
    mesh = iou.normalize_mesh(trimesh.load(gt, force='mesh'))
    best = {'iou': 0.0, 'kind': None}
    for c in se.propose(mesh):
        stl = os.path.join(outdir, f'{part}_{c["kind"]}.stl')
        with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as f:
            f.write(generate_generic_script(c['code'], stl))
        try:
            subprocess.run([sys.executable, f.name], capture_output=True, timeout=300)
        except subprocess.TimeoutExpired:
            pass
        os.unlink(f.name)
        if os.path.exists(stl):
            j = score.robust_iou(gt, stl)['iou']
            if j > best['iou']:
                best = {'iou': j, 'kind': c['kind']}
            os.unlink(stl)
    return part, best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True)
    ap.add_argument('--stl-dir', required=True)
    ap.add_argument('--scores', required=True, help='score.py --cad output that includes this run')
    ap.add_argument('--out', required=True)
    ap.add_argument('--jobs', type=int, default=16)
    a = ap.parse_args()
    name = os.path.basename(a.run.rstrip('/'))
    pipe = json.load(open(a.scores))[name]
    parts = sorted(p for p in pipe)
    outdir = tempfile.mkdtemp(prefix='secctl_', dir=os.path.join(ROOT, 'scratch'))
    jobs = [(p, os.path.join(a.stl_dir, p + '.stl'), outdir) for p in parts]
    with ProcessPoolExecutor(a.jobs) as ex:
        sec = dict(ex.map(one, jobs))
    res = {}
    for p in parts:
        pi = pipe[p]['iou'] if pipe[p] else 0.0
        pc = pipe[p].get('iou_cad', pi) if pipe[p] else 0.0
        s = sec[p]['iou']
        pg = pipe[p].get('iou_cad_gated', 0.0) if pipe[p] else 0.0
        # Section extrusions assert OCC validity in their program, so a scored one is a
        # valid delivery. best_of_gated: the better valid delivery by executed score.
        res[p] = {'pipeline': pi, 'pipeline_cad': pc, 'pipeline_gated': pg, 'sections': s,
                  'section_kind': sec[p]['kind'], 'best_of': max(pi, s), 'best_of_cad': s if s > pi else pc,
                  'best_of_gated': max(pg, s)}
    json.dump(res, open(a.out, 'w'), indent=1)
    n = len(parts)
    for k in ('pipeline', 'pipeline_cad', 'pipeline_gated', 'sections', 'best_of', 'best_of_cad', 'best_of_gated'):
        print(f'{k:<14} mean {sum(r[k] for r in res.values()) / n:.4f}  (n={n})')
    print('section chosen over pipeline on', sum(r['sections'] > r['pipeline'] for r in res.values()), 'parts')


if __name__ == '__main__':
    main()

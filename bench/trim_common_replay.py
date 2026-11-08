#!/usr/bin/env python3
"""
Replay every delivered trim-arm program under the common protocol (score.py: sandboxed
cad_replay with the 900 s limit, OCC validity of the shape and every solid, robust judge),
instead of the trim stage's own 600 s replay records (paper Sec. 4; review round 2).

The delivered program of each part is the one trim_posthoc selected (record field
"program", with its tessellation "stl" next to it); a part with no selected program scores 0.

  python bench/trim_common_replay.py bench/runs/h2s0_v3_trim.json --stl-dir bench/cadbench/fresh2 \
      --jobs 8 --out bench/runs/h2s0_v3_trim_common.json
"""
import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'bench'))


def one(job):
    import score
    part, gt, rec = job
    prog, stl = rec.get('program'), rec.get('stl')
    if not prog or not os.path.exists(prog):
        return part, {'iou_cad_gated': 0.0, 'cad_valid': False, 'cad_built': False, 'cad_error': 'no selected program'}
    recon = os.path.splitext(prog)[0] + '.stl'  # cad_replay runs <recon>.py and writes <recon>_cad.stl
    if not os.path.exists(recon):
        recon = stl
    return part, score._score_part(gt, recon, True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('trim')
    ap.add_argument('--stl-dir', required=True)
    ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    recs = json.load(open(a.trim))
    man = [it['file_id'] for it in json.load(open(os.path.join(a.stl_dir, 'manifest.json')))]
    jobs = [(p, os.path.join(a.stl_dir, p + '.stl'), recs.get(p, {})) for p in man]
    out = {}
    with ProcessPoolExecutor(a.jobs) as ex:
        for f in as_completed([ex.submit(one, j) for j in jobs]):
            p, r = f.result()
            out[p] = r
            print(p[:8], r.get('iou_cad_gated'), r.get('cad_valid'), r.get('cad_error'), flush=True)
    json.dump(out, open(a.out, 'w'), indent=1)
    v = [r.get('iou_cad_gated', 0.0) for r in out.values()]
    print(f'{len(v)} parts, gated mean {sum(v) / len(v):.4f}, valid {sum(bool(r.get("cad_valid")) for r in out.values())}')


if __name__ == '__main__':
    main()

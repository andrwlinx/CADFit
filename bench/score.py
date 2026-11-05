#!/usr/bin/env python3
"""
Independent quality judge for benchmark arms.

Scores a reconstruction against its ground truth with alpha-wrap forced on BOTH
meshes before the manifold boolean, so the result cannot be inflated by the
self-overlap failure in stock `iou.py`, and reports the volume identity check.
Used for every arm so a metric bug cannot flatter any of them.

Usage:
  python bench/score.py <gt.stl> <recon.stl>
  python bench/score.py --arms bench/runs/arms_synth --stl-dir bench/synthetic [--out scores.json]
  python bench/score.py --runs bench/runs/A bench/runs/B --stl-dir bench/cadbench/smoke
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

import trimesh

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import iou  # noqa: E402
from gwn_repair import _gwn_fast, _gwn_tri  # noqa: E402,F401


def _gwn(mesh, Q, max_elems=1_000_000):
    """Generalized winding number of each query point (Jacobson et al. 2013):
    ~1 inside, ~0 outside, robust to cracks and duplicate shells. Queries are
    chunked so each (queries x triangles x 3) temporary stays near
    `max_elems` entries whatever the mesh size."""
    import numpy as np
    T = mesh.triangles
    chunk = max(1, max_elems // max(len(T), 1))
    out = np.zeros(len(Q))
    for s in range(0, len(Q), chunk):
        q = Q[s:s + chunk]
        a = T[None, :, 0, :] - q[:, None, :]
        b = T[None, :, 1, :] - q[:, None, :]
        c = T[None, :, 2, :] - q[:, None, :]
        la, lb, lc = (np.linalg.norm(x, axis=2) for x in (a, b, c))
        det = np.einsum('ijk,ijk->ij', a, np.cross(b, c))
        den = (la * lb * lc + np.einsum('ijk,ijk->ij', a, b) * lc
               + np.einsum('ijk,ijk->ij', b, c) * la + np.einsum('ijk,ijk->ij', c, a) * lb)
        out[s:s + chunk] = (2 * np.arctan2(det, den)).sum(1) / (4 * np.pi)
    return out


def soup_iou(gt_path, recon_path, n=100000, seed=0, min_union=10000, max_chunks=10):
    """IoU for a ground truth that is an open triangle soup (raw ABC meshes:
    most are not watertight, some split into 1e5 disconnected triangles), so
    neither manifold booleans nor alpha-wrap describe its solid. Both shapes
    are labelled by generalized winding number on seeded uniform points.

    Points are drawn in the GT's bounding box (padded 1%), not a fixed cube:
    thin parts filled ~0.1% of the old [-1.05,1.05]^3 cube (abc40 00001081:
    94 union samples, SE ~0.05). Reconstruction material outside that box
    cannot overlap the GT, so it is counted with points at the same density
    drawn from the part of the reconstruction's box outside the GT box (the
    old cube clipped it: abc60 00000156). Chunks of `n` points are added until
    the union holds `min_union` samples (SE <= ~0.005) or `max_chunks` is
    reached. GT labels are cached per chunk next to the GT (.gtcache/)."""
    import numpy as np
    gt = iou.normalize_mesh(trimesh.load(gt_path, force='mesh'))
    pad = 0.01 * float(np.ptp(gt.bounds, axis=0).max())
    glo, ghi = gt.bounds[0] - pad, gt.bounds[1] + pad
    rc = trimesh.load(recon_path, force='mesh')
    rlo, rhi = rc.bounds[0] - pad, rc.bounds[1] + pad
    gvol = float(np.prod(ghi - glo))
    rvol = float(np.prod(np.maximum(rhi - rlo, 0)))
    tag = os.path.splitext(os.path.basename(gt_path))[0]
    inter = union = total = 0
    for k in range(max_chunks):
        rng = np.random.default_rng([seed, k])
        Q = rng.uniform(glo, ghi, (n, 3))
        cache = os.path.join(os.path.dirname(gt_path), '.gtcache', f'{tag}_bbox_n{n}_s{seed}_c{k}.npy')
        if os.path.exists(cache):
            in_gt = np.load(cache)
        else:
            in_gt = _gwn_fast(gt, Q) > 0.5
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            tmp = f"{cache}.{os.getpid()}.npy"  # parallel scorers of one GT must not read a partial file
            np.save(tmp, in_gt)
            os.replace(tmp, cache)
        in_rc = _gwn_fast(rc, Q) > 0.5
        inter += int((in_gt & in_rc).sum())
        union += int((in_gt | in_rc).sum())
        # Same density over the reconstruction's box; keep points outside the GT box.
        m = rng.poisson(n * rvol / gvol) if rvol > 0 else 0
        if m:
            R = rng.uniform(rlo, rhi, (m, 3))
            R = R[np.any((R < glo) | (R > ghi), axis=1)]
            if len(R):
                union += int((_gwn_fast(rc, R) > 0.5).sum())
        total += n
        if union >= min_union:
            break
    j = inter / union if union else 0.0
    return {'iou': float(j), 'method': 'gwn-mc-soup', 'union_samples': union, 'points': total,
            'se': float(np.sqrt(j * (1 - j) / union)) if union else None}


def robust_iou(gt_path, recon_path, n=40000, seed=0, min_union=10000, max_batches=5):
    """Judge that does not depend on how clean the reconstruction's STL is.

    GT (a clean CADBench solid) is normalized to [-1,1]. If the reconstruction
    is a closed, consistently wound volume, IoU is exact (manifold3d booleans,
    bodies unioned). Otherwise, e.g. an exact-union result cracked by the
    STL float32 round trip, IoU is a seeded Monte Carlo estimate in which the
    reconstruction's inside test is the generalized winding number. (Alpha-wrap
    turns such meshes into hollow shells: 0.078 against a true ~0.91.)"""
    import numpy as np
    gt = iou.normalize_mesh(trimesh.load(gt_path, force='mesh'))
    rc = trimesh.load(recon_path, force='mesh')
    # A GT that is not watertight gets no exact path. Its alpha wrap is a different,
    # fatter solid: on 00966049 (a 0.104-thick plate) the wrap has 1.21x the volume,
    # and a closed reconstruction judged against it scored 0.821, where the STEP
    # solid gives 0.958 (exact boolean of the tessellations) and the winding-number
    # estimate below 0.950. The same program, exported with a crack, had been judged
    # by that estimate, so the exact-vs-MC split decided a 0.13 "regression".
    ma = iou._to_manifold(gt) if gt.is_watertight else None
    closed = rc.is_watertight and rc.is_winding_consistent and rc.volume > 0
    mb = None
    if closed:
        mb = iou._bodies_union_manifold(rc) if rc.body_count > 1 else iou._to_manifold(rc)
    if ma is not None and mb is not None:
        vols = iou._boolean_volumes(ma, mb)
        if vols is not None and iou._volumes_consistent(ma, mb, *vols):
            return {'iou': vols[0] / vols[1] if vols[1] > 0 else 0.0, 'method': 'exact'}
    lo = np.minimum(gt.bounds[0], rc.bounds[0]) - 0.01
    hi = np.maximum(gt.bounds[1], rc.bounds[1]) + 0.01
    rng = np.random.default_rng(seed)
    inter = u = 0
    # Thin parts fill little of their box (00966049: 2,765 of 40,000 samples in the
    # union, se 0.004): draw further batches until the union has min_union samples.
    for _ in range(max_batches):
        Q = rng.uniform(lo, hi, (n, 3))
        if gt.is_watertight:  # ray-cast containment; chunked, its memory grows with rays x hits
            # (x triangles: 4000 rays on a 1e6-triangle GT took > 200 GB). Same labels, any chunk.
            step = max(250, 4000 * 100_000 // max(len(gt.faces), 100_000))
            in_gt = np.concatenate([gt.contains(Q[s:s + step]) for s in range(0, len(Q), step)])
        else:
            in_gt = _gwn(gt, Q) > 0.5
        in_rc = _gwn(rc, Q) > 0.5
        inter += int((in_gt & in_rc).sum())
        u += int((in_gt | in_rc).sum())
        if u >= min_union:
            break
    j = inter / u if u else 0.0
    return {'iou': j, 'method': 'gwn-mc', 'union_samples': u, 'se': float(np.sqrt(j * (1 - j) / u)) if u else None}


def strict_iou(gt_path, recon_path):
    gt = iou.normalize_mesh(trimesh.load(gt_path, force='mesh'))
    rc = trimesh.load(recon_path, force='mesh')
    ma = iou._to_manifold(iou._alpha_wrap(gt))
    mb = iou._to_manifold(iou._alpha_wrap(rc))
    if ma is None or mb is None:
        return {'iou': 0.0, 'consistent': False, 'note': 'manifold construction failed'}
    vols = iou._boolean_volumes(ma, mb)
    if vols is None:
        return {'iou': 0.0, 'consistent': False, 'note': 'boolean failed'}
    v_inter, v_uni = vols
    ok = iou._volumes_consistent(ma, mb, v_inter, v_uni)
    return {'iou': (v_inter / v_uni) if v_uni > 0 else 0.0, 'consistent': bool(ok),
            'vol_gt': abs(ma.volume()), 'vol_recon': abs(mb.volume()), 'inter': v_inter, 'union': v_uni}


JUDGE = 'robust'   # --judge wrap restores the phase-2 alpha-wrap judge


def judge(gt, recon):
    if JUDGE == 'soup':
        # Watertight GTs keep the exact judge; soups get winding-number labels.
        return robust_iou(gt, recon) if trimesh.load(gt, force='mesh').is_watertight else soup_iou(gt, recon)
    return robust_iou(gt, recon) if JUDGE == 'robust' else strict_iou(gt, recon)


RUN_RECON = ('best_greedy_parallel_iterative.stl', 'best_greedy_parallel.stl')


def chamfer(gt_path, recon_path, n=20000, seed=0):
    """Symmetric mean L2 chamfer distance in the normalized [-1,1] frame."""
    from scipy.spatial import cKDTree
    gt = iou.normalize_mesh(trimesh.load(gt_path, force='mesh'))
    rc = trimesh.load(recon_path, force='mesh')
    a, _ = trimesh.sample.sample_surface(gt, n, seed=seed)
    b, _ = trimesh.sample.sample_surface(rc, n, seed=seed)
    return float(0.5 * (cKDTree(b).query(a)[0].mean() + cKDTree(a).query(b)[0].mean()))


def env_failure(error):
    """The replay failures eligible for one recovery evaluation (HELDOUT_PROTOCOL.md,
    amendment 2026-11-05): 'setup' = the sandbox could not be set up (no evaluation took
    place); 'resource' = killed (rc -9) or over the 900 s limit, which may be the machine
    or the program. Returns the class, or None for any other outcome. Every outcome is
    cached; bench/h2_env_clear.py clears an eligible part once, and the recovery result
    is terminal."""
    e = str(error or '')
    if 'ns_sandbox' in e:
        return 'setup'
    if e == 'timeout 900s' or '(rc -9,' in e:
        return 'resource'
    return None


def cad_replay(recon, timeout=900):
    """Run the CadQuery program saved next to `recon` (same name, .py) in a fresh
    process (bench/cad_replay.py) and return its record; the rebuilt STL is
    written next to it as <name>_cad.stl. Cached in <name>_cad.json."""
    base = os.path.splitext(recon)[0]
    prog, out_stl, rec_path = base + '.py', base + '_cad.stl', base + '_cad.json'
    if os.path.exists(rec_path) and os.path.getmtime(rec_path) >= os.path.getmtime(prog):
        return json.load(open(rec_path)), out_stl
    if not os.path.exists(prog):
        return {'built': False, 'valid': False, 'error': 'no program'}, out_stl
    # The program may hold agent-written code (agent_model.py): run it in the same
    # sandbox as the agent's episode (no network, writes only next to the program).
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'agent'))
    from cad_tools import _sandboxed
    argv = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cad_replay.py'),
            os.path.abspath(prog), os.path.abspath(out_stl)]
    rec = None
    for attempt in range(2):  # a replay that dies without any output is retried once
        try:
            # cwd = the program's folder on every backend (sandbox-exec does not chdir):
            # agent_model.py exports to a relative path.
            p = subprocess.run(_sandboxed(os.path.dirname(os.path.abspath(prog)), argv), capture_output=True,
                               text=True, timeout=timeout, cwd=os.path.dirname(os.path.abspath(prog)))
        except subprocess.TimeoutExpired:
            rec = {'built': False, 'valid': False, 'error': f'timeout {timeout}s'}
            break
        lines = p.stdout.strip().splitlines()
        try:
            rec = json.loads(lines[-1])
            break
        except (IndexError, json.JSONDecodeError):
            # no record: the replay process crashed (e.g. an OCC segfault) — it does not build
            rec = {'built': False, 'valid': False,
                   'error': f'replay crashed (rc {p.returncode}, attempt {attempt + 1}): {p.stderr.strip()[-300:]}'}
            if lines:
                break  # it printed something else: a real failure, not a silent death
    json.dump(rec, open(rec_path, 'w'))
    return rec, out_stl


def _score_one(job):
    name, part, gt, recon, judge_name, cad = job
    global JUDGE
    JUDGE = judge_name  # a spawned worker does not inherit main()'s setting
    # Per-part result cache (I/O only, values unchanged): a run killed at its time
    # limit or preempted resumes instead of judging every part again. Valid while
    # the reconstruction is not newer than the cache.
    cache = f'{os.path.splitext(recon)[0]}_score_{judge_name}{"_cad" if cad else ""}.json'
    if os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(recon):
        return name, part, json.load(open(cache))
    r = _score_part(gt, recon, cad)
    json.dump(r, open(cache, 'w'))
    return name, part, r


def _score_part(gt, recon, cad):
    r = judge(gt, recon)
    r['cd'] = chamfer(gt, recon)
    r['valid'] = True
    if cad:
        # Mesh fidelity (iou) and executable-CAD fidelity (iou_cad) are reported
        # separately: iou_cad judges the geometry the program rebuilds, 0 if it
        # does not build; cad_valid is OCC validity of that shape and its solids.
        rec, stl = cad_replay(recon)
        r['cad_built'], r['cad_valid'] = rec['built'], rec['valid']
        r['cad_error'] = rec.get('error')
        if rec['built'] and os.path.exists(stl):
            jc = judge(gt, stl)
            r['iou_cad'] = jc['iou']
            r['cad_judge'] = {k: v for k, v in jc.items() if k != 'iou'}  # method, MC se/samples
        else:
            r['iou_cad'] = 0.0
        # Primary metric (ledger A-050): executed CAD IoU, 0 unless built and OCC-valid.
        r['iou_cad_gated'] = r['iou_cad'] if rec['valid'] else 0.0
    return r


def _init_worker():
    # One numpy thread per worker: the parallelism is across parts.
    for v in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[v] = '1'


def score_runs(run_dirs, stl_dir, jobs=1, cad=False):
    """Score full-pipeline output folders (run_pipeline.py --output-folder).
    A part with no reconstruction counts as invalid with IoU 0. With jobs > 1,
    parts are scored in that many processes (each part is serial numpy, so a
    60-part, 2-arm run used ~16 of 88 threads and took about an hour)."""
    parts = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(stl_dir, '*.stl')))
    # A part is still running if a live process of this run names it. Orphans
    # (parent 1: pool workers left by a timed-out part) do not count; they
    # used to keep finished parts from ever being scored.
    procs = []
    for line in subprocess.run(['ps', '-Ao', 'ppid=,command='], capture_output=True, text=True).stdout.splitlines():
        ppid, _, cmd = line.strip().partition(' ')
        if ppid != '1':
            procs.append(cmd)
    out, todo = {}, []
    for run in run_dirs:
        name = os.path.basename(run.rstrip('/'))
        if not any(os.path.isdir(os.path.join(run, p)) for p in parts):
            continue  # an input copy or code snapshot folder, not a run
        mine = [c for c in procs if re.search(r'(^|[/\s])' + re.escape(name) + r'(_in)?(/|\s|$)', c)]
        running = {p for p in parts if any(p + '.stl' in c or '/' + p + '/' in c for c in mine)}
        res = {}
        for part in parts:
            if part in running and not os.path.exists(os.path.join(run, part, 'final_iou.json')):
                continue  # still running: its STLs are intermediate (a crash still scores invalid)
            recon = next((os.path.join(run, part, r) for r in RUN_RECON
                          if os.path.exists(os.path.join(run, part, r))), None)
            if recon is None:
                # Every part of the cohort is in the denominator: a part that
                # crashed (folder, no model) or never started (no folder, e.g. a
                # job cut short) scores 0, and the record says which.
                res[part] = {'iou': 0.0, 'cd': None, 'valid': False,
                             'status': 'no_model' if os.path.isdir(os.path.join(run, part)) else 'not_run'}
                if cad:
                    res[part].update(iou_cad=0.0, iou_cad_gated=0.0, cad_built=False, cad_valid=False)
                continue
            res[part] = None  # filled in below
            todo.append((name, part, os.path.join(stl_dir, part + '.stl'), recon, JUDGE, cad))
        out[name] = res

    def done(name, part, r):
        out[name][part] = r
        print(f"{name:<22} {part[:40]:<40} iou={r['iou']:.4f} cd={r['cd']:.4f}"
              + (f" iou_cad={r['iou_cad']:.4f} cad_valid={r['cad_valid']}" if 'iou_cad' in r else ''), flush=True)
    if jobs > 1 and len(todo) > 1:
        import multiprocessing as mp
        from concurrent.futures import ProcessPoolExecutor, as_completed
        from concurrent.futures.process import BrokenProcessPool
        # A judge can take ~22 GB (gwn-mc on a large part); a few at once can
        # exhaust RAM and the OOM killer breaks the whole pool. Rerun what is
        # left with half the workers, down to one, instead of losing the run.
        while todo:
            left = {}
            try:
                # spawn: workers start clean instead of inheriting this process's state.
                with ProcessPoolExecutor(min(jobs, len(todo)), mp_context=mp.get_context('spawn'),
                                         initializer=_init_worker) as ex:
                    left = {ex.submit(_score_one, j): j for j in todo}
                    for f in as_completed(left):
                        done(*f.result())
                        del left[f]
                todo = []
            except BrokenProcessPool:
                if jobs == 1:
                    raise
                todo, jobs = list(left.values()), max(1, jobs // 2)
                print(f'worker died (likely OOM); rescoring {len(todo)} parts with {jobs} jobs', flush=True)
    else:
        for j in todo:
            done(*_score_one(j))
    common = set.intersection(*(set(v) for v in out.values())) if out else set()
    print(f'\n{len(common)} parts scored by every run')
    for name, res in out.items():
        ious = [res[p]['iou'] for p in common]
        cds = [res[p]['cd'] for p in common if res[p]['cd'] is not None]
        inval = sum(not res[p]['valid'] for p in common)
        if ious:
            line = f'{name:<22} mean IoU {sum(ious) / len(ious):.4f}  mean CD {sum(cds) / max(len(cds), 1):.4f}  invalid {inval}'
            if cad:
                ic = [res[p].get('iou_cad', 0.0) for p in common]
                bad = sum(not res[p].get('cad_valid', False) for p in common)
                ig = [res[p].get('iou_cad_gated', 0.0) for p in common]
                line += (f'  mean IoU(CAD) {sum(ic) / len(ic):.4f}  gated {sum(ig) / len(ig):.4f}'
                         f'  CAD invalid/unbuilt {bad}')
            nr = sum(res[p].get('status') == 'not_run' for p in res)
            print(line + (f'  NOT RUN {nr}' if nr else ''))
    return out


def main():
    ap = argparse.ArgumentParser(description='Strict IoU judge')
    ap.add_argument('paths', nargs='*')
    ap.add_argument('--arms', help='arms folder from bench/run_arms.sh')
    ap.add_argument('--runs', nargs='+', help='full-pipeline output folders to score side by side')
    ap.add_argument('--stl-dir')
    ap.add_argument('--recon', default='best_greedy_parallel.stl')
    ap.add_argument('--out')
    ap.add_argument('--jobs', type=int, default=1,
                    help='score --runs parts in this many processes (e.g. nproc/2 on the workstation)')
    ap.add_argument('--judge', choices=['robust', 'wrap', 'soup'], default='robust',
                    help='robust: exact booleans, winding-number MC for unclean meshes (default); '
                         'wrap: alpha-wrap both meshes (phase-2 judge); '
                         'soup: like robust, but a non-watertight GT (raw ABC triangle soup) is labelled '
                         'by winding number on 1e5 cached seeded points')
    ap.add_argument('--cad', action='store_true',
                    help='also replay each part\'s CadQuery program, check OCC validity and judge the rebuilt shape')
    args = ap.parse_args()
    global JUDGE
    JUDGE = args.judge

    if args.runs:
        out = score_runs(args.runs, args.stl_dir, jobs=args.jobs, cad=args.cad)
        if args.out:
            json.dump(out, open(args.out, 'w'), indent=2)
    elif args.arms:
        out = {}
        for done in sorted(glob.glob(os.path.join(args.arms, '*', '*', 'done'))):
            folder = os.path.dirname(done)
            arm, part = folder.split(os.sep)[-2:]
            gt = os.path.join(args.stl_dir, part + '.stl')
            recon = os.path.join(folder, args.recon)
            if not (os.path.exists(gt) and os.path.exists(recon)):
                out.setdefault(arm, {})[part] = None
                continue
            r = strict_iou(gt, recon)
            out.setdefault(arm, {})[part] = r
            print(f"{arm:<14} {part:<22} iou={r['iou']:.4f} consistent={r['consistent']}")
        if args.out:
            json.dump(out, open(args.out, 'w'), indent=2)
    else:
        gt, recon = args.paths
        # --cad: replay the program saved next to recon (same name, .py) and judge what it builds
        print(json.dumps(_score_part(gt, recon, True) if args.cad else judge(gt, recon), indent=2))


if __name__ == '__main__':
    main()

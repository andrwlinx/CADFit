#!/usr/bin/env python3
"""
Offline oracle for the CADFit++ candidate ranker.

Uses kept-history folders of *stock* runs (run_pipeline.py --keep-history), in
which every candidate was kernel-evaluated, and asks: had the ranker filtered
the candidates first, what would have been lost and how much saved? No CadQuery
is re-run.

Per run folder it needs: loops_split.json, loops_split_revolve.json,
revolve_analysis/, precomputed_operations.json, evaluated_operations.json and
(optionally) greedy_extrusion_data.json, plus the ground-truth STL.

Usage:
  python bench/oracle_eval.py --runs bench/runs/stock --stl-dirs bench/synthetic bench/smoke \
      --out bench/runs/oracle.json
"""
import argparse
import contextlib
import glob
import io
import json
import os
import sys

import numpy as np
import trimesh
from scipy.stats import spearmanr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from iou import normalize_mesh  # noqa: E402
from greedy_search import _build_split_entry_for_revolve, load_revolve_analysis  # noqa: E402
import candidate_ranker as cr  # noqa: E402

PRUNE_FLOOR = 1e-2  # cadquery_ops.greedy_iou_based_pruning drops individual_iou below this


def op_key(op):
    return (op['type'], op['sketch_idx'], str(op.get('source') if op['type'] == 'extrude' else op.get('axis_idx')))


def metas_from_history(folder, operations):
    """Rebuild the ranker's per-candidate geometry from a stock run's files."""
    loops = json.load(open(os.path.join(folder, 'loops_split.json')))
    rloops = json.load(open(os.path.join(folder, 'loops_split_revolve.json')))
    rfolder = os.path.join(folder, 'revolve_analysis')
    metas = []
    for op in operations:
        if op['type'] == 'extrude':
            metas.append({'profile_3d': loops[op['sketch_idx']].get('loops_3d')})
            continue
        meta = None
        for cfg in load_revolve_analysis(rfolder, op['sketch_idx']):
            if str(cfg.get('axis_idx')) != str(op.get('axis_idx')):
                continue
            with contextlib.redirect_stdout(io.StringIO()):
                split, mp_w, ad_w = _build_split_entry_for_revolve(
                    rloops[op['sketch_idx']], np.array(cfg['mean_point']), np.array(cfg['axis_direction']))
            if split is not None:
                meta = {'profile_3d': split['loops_3d'], 'axis_point': mp_w.tolist(), 'axis_dir': ad_w.tolist()}
            break
        metas.append(meta)
    return metas


def evaluate_run(folder, stl_path, normalize=True, n_points=20000):
    ops = json.load(open(os.path.join(folder, 'precomputed_operations.json')))['operations']
    evaluated = json.load(open(os.path.join(folder, 'evaluated_operations.json')))
    true_iou = {op_key(o): float(o['iou']) for o in evaluated}
    y = np.array([true_iou.get(op_key(o), 0.0) for o in ops])

    gt = trimesh.load(stl_path, force='mesh')
    if normalize:
        gt = normalize_mesh(gt)
    ctx = cr.build_context(gt, n_points=n_points, seed=0)
    metas = metas_from_history(folder, ops)

    selected_keys = set()
    sel_path = os.path.join(folder, 'greedy_extrusion_data.json')
    if os.path.exists(sel_path):
        data = json.load(open(sel_path))
        rows = data.get('candidates', data) if isinstance(data, dict) else data
        for row in rows:
            if not row.get('selected'):
                continue
            want = 'revolve' if row.get('type') == 'revolve' else 'extrude'
            members = [i for i, o in enumerate(ops) if o['type'] == want and o['sketch_idx'] == row['sketch_idx']]
            if members:
                selected_keys.add(op_key(ops[max(members, key=lambda i: y[i])]))

    groups = {}
    for i, o in enumerate(ops):
        groups.setdefault(cr.group_key(o), []).append(i)

    out = {'stl': os.path.basename(stl_path), 'N': len(ops), 'G': len(groups),
           'n_selected': len(selected_keys), 'rankers': {}}
    for name, scorer in (('proxy', cr.score_candidate), ('heuristic', cr.score_candidate_heuristic)):
        _, diag = cr.rank_candidates(ops, metas, ctx, per_group_m=1, scorer=scorer)
        s = np.array([(-1.0 if d['score'] is None else d['score']) for d in diag])
        res = {'spearman': float(spearmanr(s, y).correlation) if len(ops) > 2 and np.ptp(y) > 0 and np.ptp(s) > 0 else None}
        if name == 'proxy':
            p = np.array([np.nan if d['proxy_iou'] is None else d['proxy_iou'] for d in diag])
            ok = ~np.isnan(p)
            res['proxy_mae'] = float(np.mean(np.abs(p[ok] - y[ok]))) if ok.any() else None
            res['proxy_missing'] = int((~ok).sum())
        for m in (1, 2):
            kept, d = cr.rank_candidates(ops, metas, ctx, per_group_m=m, scorer=scorer)
            retained = np.array([r['retained'] for r in d])
            hits, regrets, multi = 0, [], 0
            for idxs in groups.values():
                best = max(y[i] for i in idxs)
                best_kept = max(y[i] for i in idxs if retained[i])
                regrets.append(best - best_kept)
                if len(idxs) > 1:
                    multi += 1
                    hits += best - best_kept <= 1e-9
            sel_recall = (sum(retained[i] for i, o in enumerate(ops) if op_key(o) in selected_keys) / len(selected_keys)
                          if selected_keys else None)
            res[f'm{m}'] = {'kept': int(retained.sum()), 'multi_groups': multi,
                            'top_acc_multi': hits / multi if multi else None,
                            'max_regret': float(max(regrets)), 'mean_regret': float(np.mean(regrets)),
                            'best_single_kept': bool(retained[int(np.argmax(y))]),
                            'selected_recall': sel_recall}
        out['rankers'][name] = res

    # Whole-group dropping: which groups are useless (below the pruning floor)
    # and how many does a proxy threshold catch without touching useful ones?
    _, diag = cr.rank_candidates(ops, metas, ctx, per_group_m=1)
    out['drop'] = {}
    for tau in (0.001, 0.002, 0.005):
        dropped = useless = false_drop = evals_saved = 0
        for idxs in groups.values():
            sc = [float('inf') if diag[i]['score'] is None else diag[i]['score'] for i in idxs]
            best_true = max(y[i] for i in idxs)
            useless += best_true < PRUNE_FLOOR
            if max(sc) < tau:
                dropped += 1
                evals_saved += len(idxs)
                false_drop += best_true >= PRUNE_FLOOR
        out['drop'][str(tau)] = {'groups_dropped': dropped, 'groups_useless': int(useless),
                                 'false_drops': int(false_drop), 'evals_saved': evals_saved}
    return out


def main():
    ap = argparse.ArgumentParser(description='Offline oracle evaluation of the candidate ranker')
    ap.add_argument('--runs', required=True, help='Folder of kept-history stock runs (<runs>/<stl_id>/)')
    ap.add_argument('--stl-dirs', nargs='+', required=True, help='Folders holding the ground-truth STLs')
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    results = []
    for folder in sorted(glob.glob(os.path.join(args.runs, '*'))):
        if not os.path.exists(os.path.join(folder, 'evaluated_operations.json')):
            continue
        stl_id = os.path.basename(folder)
        # Prefer the run's own (possibly repaired/decimated) copy of the GT if present.
        stl = next((p for d in args.stl_dirs for p in [os.path.join(d, stl_id + '.stl')] if os.path.exists(p)), None)
        if stl is None:
            print(f'{stl_id}: ground-truth STL not found, skipping')
            continue
        try:
            r = evaluate_run(folder, stl)
        except Exception as e:
            print(f'{stl_id}: FAILED {e}')
            continue
        results.append(r)
        p = r['rankers']['proxy']
        print(f"{stl_id}: N={r['N']} G={r['G']} spearman={p['spearman']} mae={p.get('proxy_mae')} "
              f"m1: kept={p['m1']['kept']} acc={p['m1']['top_acc_multi']} maxregret={p['m1']['max_regret']:.4f} "
              f"selrecall={p['m1']['selected_recall']}")

    if args.out:
        with open(args.out, 'w') as f:
            json.dump(results, f, indent=2)
        print(f'Wrote {args.out}')


if __name__ == '__main__':
    main()

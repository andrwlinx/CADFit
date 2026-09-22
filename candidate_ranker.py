#!/usr/bin/env python3
"""
CADFit++ candidate ranking.

Scores extrusion/revolve candidates *before* they are built through CadQuery,
so that only the promising ones reach the expensive kernel + boolean-IoU
evaluation in greedy_search.py.

The primary score is a proxy IoU that needs no CAD kernel:
  - sample points inside the ground-truth mesh once,
  - test them analytically against the candidate solid (prism: in-plane
    point-in-polygon + height range; revolve: point-in-polygon in (r, z)
    coordinates about the axis),
  - take the candidate volume analytically (area x height, or Pappus),
  - IoU ~= f*V_gt / (V_gt + V_cand - f*V_gt), f = fraction of GT points inside.

Selection keeps the top `per_group_m` candidates of every
(operation type, sketch_idx) group, because greedy_search collapses each group
to its best member anyway; an optional global budget fills up from the rest.
"""
import math
from typing import Any, Dict, List, Optional

import numpy as np
import shapely
from shapely.geometry import Polygon

from fit_primitives import plane_basis


def sample_points_inside(mesh, n_points: int = 20000, seed: int = 0, max_batches: int = 40):
    """Rejection-sample points uniformly inside a watertight mesh."""
    rng = np.random.default_rng(seed)
    lo, hi = mesh.bounds
    out, have = [], 0
    for _ in range(max_batches):
        pts = rng.uniform(lo, hi, size=(n_points, 3))
        inside = pts[mesh.contains(pts)]
        out.append(inside)
        have += len(inside)
        if have >= n_points:
            break
    if not out:
        return np.zeros((0, 3))
    return np.vstack(out)[:n_points]


def build_context(gt_mesh, n_points: int = 20000, seed: int = 0) -> Dict[str, Any]:
    """Per-run data shared by all candidates: GT interior samples and volume."""
    return {
        'gt_points': sample_points_inside(gt_mesh, n_points=n_points, seed=seed),
        'gt_volume': float(abs(gt_mesh.volume)),
    }


def _even_odd_region(loops_2d: List[np.ndarray]):
    """Combine closed 2D loops with the even-odd rule (outer minus holes,
    whatever the nesting). Returns a shapely geometry or None."""
    region = None
    for pts in loops_2d:
        if len(pts) < 3:
            continue
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty:
            continue
        region = poly if region is None else region.symmetric_difference(poly)
    if region is None or region.is_empty:
        return None
    return region


def _contains(region, xy: np.ndarray) -> np.ndarray:
    shapely.prepare(region)
    return shapely.contains_xy(region, xy[:, 0], xy[:, 1])


def _extrude_inside_and_volume(op: Dict, meta: Dict, pts: np.ndarray):
    u, v, n = plane_basis(op['normal'], op.get('xdir'))
    origin = np.asarray(op['origin'], dtype=float)
    loops_2d = []
    for loop in meta['profile_3d']:
        rel = np.asarray(loop, dtype=float) - origin
        loops_2d.append(np.column_stack([rel.dot(u), rel.dot(v)]))
    region = _even_odd_region(loops_2d)
    if region is None:
        return None, 0.0, 0.0
    rel = pts - origin
    t = rel.dot(n)
    h = float(op['height'])
    inside = (t >= min(0.0, h)) & (t <= max(0.0, h))
    inside &= _contains(region, np.column_stack([rel.dot(u), rel.dot(v)]))
    return inside, float(region.area * abs(h)), float(region.area)


def _revolve_inside_and_volume(op: Dict, meta: Dict, pts: np.ndarray):
    a = np.asarray(meta['axis_dir'], dtype=float)
    a = a / (np.linalg.norm(a) + 1e-12)
    p0 = np.asarray(meta['axis_point'], dtype=float)

    def to_rz(x):
        d = np.asarray(x, dtype=float) - p0
        z = d.dot(a)
        r = np.linalg.norm(d - z[:, None] * a[None, :], axis=1)
        return np.column_stack([r, z])

    region = _even_odd_region([to_rz(loop) for loop in meta['profile_3d']])
    if region is None:
        return None, 0.0, 0.0
    inside = _contains(region, to_rz(pts))
    frac = abs(float(op.get('angle', 360.0))) / 360.0
    # Pappus: V = 2*pi * (centroid radius) * area, scaled by the swept fraction
    volume = 2.0 * math.pi * max(region.centroid.x, 0.0) * region.area * frac
    return inside, float(volume), float(region.area)


def extract_candidate_features(op: Dict, meta: Optional[Dict], ctx: Dict) -> Dict[str, Any]:
    """Cheap, kernel-free features for one candidate."""
    feats = {
        'type': op['type'],
        'sketch_idx': op['sketch_idx'],
        'n_primitives': len(op.get('actions') or []),
        'proxy_iou': None,
        'gt_frac_inside': None,
        'volume': None,
        'profile_area': None,
    }
    if op['type'] == 'extrude':
        feats['height'] = float(op['height'])
        feats['interval_width'] = float(op['t_max'] - op['t_min'])
    else:
        feats['rotation_type'] = op.get('rotation_type')
    for k in ('mean_cd', 'min_cd', 'max_cd', 'symmetry_ratio'):
        if meta and meta.get(k) is not None:
            feats[k] = float(meta[k])

    pts = ctx['gt_points']
    if meta is None or not meta.get('profile_3d') or len(pts) == 0:
        return feats
    try:
        if op['type'] == 'extrude':
            inside, volume, area = _extrude_inside_and_volume(op, meta, pts)
        else:
            inside, volume, area = _revolve_inside_and_volume(op, meta, pts)
    except Exception as e:
        feats['error'] = str(e)
        return feats
    if inside is None:
        return feats

    f = float(inside.mean())
    v_gt = ctx['gt_volume']
    inter = f * v_gt
    union = v_gt + volume - inter
    feats.update(gt_frac_inside=f, volume=volume, profile_area=area,
                 proxy_iou=float(inter / union) if union > 0 else 0.0)
    return feats


def score_candidate(features: Dict[str, Any]) -> float:
    """Proxy IoU. Candidates it could not be computed for score +inf so that
    they are always kept (never drop something we could not assess)."""
    p = features.get('proxy_iou')
    return float('inf') if p is None else float(p)


def score_candidate_heuristic(features: Dict[str, Any]) -> float:
    """Metadata-only baseline ranker (no GT occupancy): prefer large, simple
    candidates. Used only as a comparison point in the offline oracle."""
    vol = features.get('volume') or 0.0
    return float(vol) - 1e-3 * float(features.get('n_primitives') or 0)


def group_key(op: Dict):
    # Extrusion and revolve sketch indices come from different loop files,
    # so the operation type is part of the key.
    return (op['type'], op['sketch_idx'])


def rank_candidates(operations: List[Dict], metas: List[Optional[Dict]], ctx: Dict,
                    per_group_m: int = 1, top_k: Optional[int] = None,
                    keep_ratio: Optional[float] = None, drop_tau: Optional[float] = None,
                    scorer=score_candidate):
    """Select which candidates reach kernel evaluation.

    Returns (kept_operations, diagnostics). `kept_operations` preserves the
    original ordering; `diagnostics` has one row per input candidate.
    """
    feats = [extract_candidate_features(op, m, ctx) for op, m in zip(operations, metas)]
    scores = [scorer(f) for f in feats]

    groups: Dict[Any, List[int]] = {}
    for i, op in enumerate(operations):
        groups.setdefault(group_key(op), []).append(i)

    keep, dropped_groups = set(), set()
    for key, idxs in groups.items():
        # Stable sort: ties keep the original order, as the stock collapse does.
        order = sorted(idxs, key=lambda i: -scores[i])
        if drop_tau is not None and scores[order[0]] < drop_tau:
            dropped_groups.add(key)
            continue
        keep.update(order[:max(1, per_group_m)])

    budget = None
    if top_k is not None:
        budget = int(top_k)
    elif keep_ratio is not None:
        budget = int(math.ceil(keep_ratio * len(operations)))
    if budget is not None and len(keep) < budget:
        rest = [i for i in range(len(operations))
                if i not in keep and group_key(operations[i]) not in dropped_groups]
        rest.sort(key=lambda i: -scores[i])
        keep.update(rest[:budget - len(keep)])

    rank_of = {i: r for r, i in enumerate(sorted(range(len(operations)), key=lambda i: -scores[i]))}
    diagnostics = []
    for i, op in enumerate(operations):
        row = dict(feats[i])
        row.update(candidate_id=i,
                   source=op.get('source', op.get('axis_idx')),
                   score=None if math.isinf(scores[i]) else scores[i],
                   rank=rank_of[i], retained=i in keep,
                   group_dropped=group_key(op) in dropped_groups)
        diagnostics.append(row)

    kept_ops = [op for i, op in enumerate(operations) if i in keep]
    return kept_ops, diagnostics

#!/usr/bin/env python3
"""
CAD Sketch Optimization using Pre-computed Analysis Results

This script uses pre-computed results from:
- analyze_loop_translation.py (for extrusion heights)
- analyze_revolve_axis.py (for revolve operations)

Instead of searching for optimal parameters, it loads them from JSON files
and directly constructs the best extrusion/revolve operations, then runs
the greedy IoU-based pruning phase.
"""
import os
import sys
import json
import argparse
import numpy as np
import trimesh
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import signal
import multiprocessing as mp
from functools import partial
from fit_primitives import build_action_instances_from_entry
from iou import normalize_mesh
from profiling import log_event
from cadquery_ops import (
    greedy_iou_based_pruning,
    execute_cadquery_script,
    generate_cadquery_script,
    compute_iou,
    generate_cadquery_revolve_script,
    generate_generic_script,
    safe_pool_map,
    guarded_pool,
)


def load_translation_analysis(analysis_folder: str, sketch_idx: int) -> Optional[Dict]:
    """
    Load translation analysis results for a sketch.
    
    Args:
        analysis_folder: Folder containing analysis JSON files
        sketch_idx: Sketch index
        
    Returns:
        Dictionary with interval data or None if file doesn't exist or has no valid intervals
    """
    json_path = os.path.join(analysis_folder, f"sketch_{sketch_idx}_intervals.json")
    
    if not os.path.exists(json_path):
        return None
    
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    # Check if there are valid intervals
    if not data.get('merged_intervals') and (data.get('all_intervals_min') is None or data.get('all_intervals_max') is None):
        return None
    
    return data


def load_revolve_analysis(analysis_folder: str, sketch_idx: int) -> List[Dict]:
    """
    Load revolve analysis results for a sketch (simplified JSONs).
    
    Args:
        analysis_folder: Folder containing analysis JSON files
        sketch_idx: Sketch index
        
    Returns:
        List of revolve configurations with axis_direction and mean_point
    """
    revolve_configs = []
    
    # Search for all simplified JSON files for this sketch
    import glob
    pattern = os.path.join(analysis_folder, f"sketch_{sketch_idx}_axis_*_simplified.json")
    
    for json_path in glob.glob(pattern):
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            if data.get('all_cd_under_threshold') and 'mean_point' in data and 'axis_direction' in data:
                revolve_configs.append(data)
        except Exception as e:
            print(f"Warning: Could not load {json_path}: {e}")
    
    return revolve_configs


def create_extrusion_from_translation(entry: Dict, translation_data: Dict, sketch_idx: int) -> List[Dict]:
    """
    Create extrusion operations from translation analysis data.
    
    Args:
        entry: Sketch entry from loops_split.json
        translation_data: Translation analysis results
        sketch_idx: Sketch index
        
    Returns:
        List of extrusion dictionaries with sketch actions and heights
    """
    extrusions = []
    
    # Get plane information
    origin = np.array(entry.get('origin', [0, 0, 0]))
    normal = np.array(entry.get('normal', [0, 0, 1]))
    normal = normal / np.linalg.norm(normal)
    
    # Use merged_intervals if available, otherwise fall back to old format
    intervals = translation_data.get('merged_intervals', [])
    
    if not intervals:
        # Fall back: build intervals from old fields
        interval_zero = translation_data.get('interval_containing_zero')
        all_min = translation_data.get('all_intervals_min')
        all_max = translation_data.get('all_intervals_max')
        if interval_zero is not None:
            intervals.append({'t_start': interval_zero['t_min'], 't_end': interval_zero['t_max']})
        if all_min is not None and all_max is not None:
            intervals.append({'t_start': all_min, 't_end': all_max})
    
    # If more than 5 intervals, keep the 5 largest by width
    if len(intervals) > 5:
        intervals = sorted(intervals, key=lambda iv: iv['t_end'] - iv['t_start'], reverse=True)[:5]
    
    import copy
    for iv_idx, interval in enumerate(intervals):
        t_min = interval['t_start']
        t_max = interval['t_end']
        
        # Move origin by t_min * normal
        new_origin = origin + t_min * normal
        height = t_max - t_min
        
        # Create modified entry with translated origin (deep copy to preserve loops_3d, etc.)
        modified_entry = copy.deepcopy(entry)
        modified_entry['origin'] = new_origin.tolist()
        
        # Build sketch action instances with modified origin
        insts = build_action_instances_from_entry(modified_entry, entry_idx=sketch_idx)
        
        if insts:
            extrusions.append({
                'type': 'extrude',
                'sketch_idx': sketch_idx,
                'actions': insts,
                'height': height,
                'origin': new_origin.tolist(),
                'normal': normal.tolist(),
                'xdir': entry.get('xdir', [1, 0, 0]),
                'source': f'interval_{iv_idx}',
                't_min': t_min,
                't_max': t_max,
                # Ranker-only metadata; stripped before serialization/evaluation.
                '_rank': {
                    'profile_3d': entry.get('loops_3d'),
                    'mean_cd': interval.get('mean_cd'),
                    'min_cd': interval.get('min_cd'),
                    'max_cd': interval.get('max_cd'),
                },
            })
    
    return extrusions


def _split_loop_along_axis_2d(pts2: np.ndarray, mp2: np.ndarray, ad2: np.ndarray):
    """Cut a closed 2D polyline by the axis line through mp2 with direction ad2.
    Keep the half whose signed perpendicular distance to the axis is positive.
    Returns a closed 2D polyline (Nx2) or None if the half is empty/degenerate.
    """
    perp = np.array([-ad2[1], ad2[0]])
    signed = (pts2 - mp2[None, :]).dot(perp)
    N = len(pts2)
    out = []
    for i in range(N):
        p, s = pts2[i], signed[i]
        sn = signed[(i + 1) % N]
        q = pts2[(i + 1) % N]
        if s >= 0:
            out.append(p)
        # Edge crosses the axis: insert the crossing point.
        # Consecutive crossings produce the on-axis closing segment automatically.
        if (s > 0 and sn < 0) or (s < 0 and sn > 0):
            t = s / (s - sn)
            out.append(p + t * (q - p))
    if len(out) < 3:
        return None
    out = np.asarray(out, dtype=float)
    if not np.allclose(out[0], out[-1]):
        out = np.vstack([out, out[0:1]])
    return out


def _refine_symmetry_axis_2d(pts2: np.ndarray, mp2: np.ndarray, ad2: np.ndarray,
                             angle_range_deg: float = 3.0, n_angle: int = 13,
                             offset_frac: float = 0.03, n_offset: int = 13):
    """Locally refine a 2D symmetry axis by minimizing reflection chamfer.
    Searches around (angle, perpendicular offset) of the initial axis."""
    import math
    from scipy.spatial import cKDTree

    # Subsample for speed
    M = len(pts2)
    if M > 500:
        idx = np.linspace(0, M - 1, 500).astype(int)
        sample = pts2[idx]
    else:
        sample = pts2

    tree = cKDTree(sample)
    bbox_diag = float(np.linalg.norm(pts2.max(axis=0) - pts2.min(axis=0)))
    init_angle = math.atan2(ad2[1], ad2[0])
    angles = np.linspace(init_angle - math.radians(angle_range_deg),
                         init_angle + math.radians(angle_range_deg), n_angle)
    offsets = np.linspace(-offset_frac * bbox_diag, offset_frac * bbox_diag, n_offset)

    best_cost = float('inf')
    best_mp, best_ad = mp2, ad2
    for ang in angles:
        ad_try = np.array([math.cos(ang), math.sin(ang)])
        perp_try = np.array([-ad_try[1], ad_try[0]])
        for off in offsets:
            mp_try = mp2 + off * perp_try
            d = (sample - mp_try).dot(perp_try)
            reflected = sample - 2.0 * d[:, None] * perp_try[None, :]
            dists, _ = tree.query(reflected)
            cost = float(np.mean(dists ** 2))
            if cost < best_cost:
                best_cost = cost
                best_mp = mp_try
                best_ad = ad_try
    return best_mp, best_ad, best_cost


def _build_split_entry_for_revolve(entry: Dict, mean_point_world: np.ndarray,
                                   axis_direction_world: np.ndarray):
    """Return a deep-copied entry with loops_3d replaced by the half-loop
    on one side of the symmetry axis. Returns None if the axis cannot be
    projected to 2D (e.g., axis is along the plane normal) or any loop fails to split.
    Also returns the refined axis (mean_point, axis_direction) in WORLD coords."""
    import copy
    from fit_primitives import plane_basis, project_points_to_plane

    origin = np.array(entry.get('origin', [0, 0, 0]), dtype=float)
    normal = entry.get('normal', [0, 0, 1])
    xdir = entry.get('xdir', [1, 0, 0])
    loops_3d = entry.get('loops_3d') or []
    if not loops_3d:
        return None, None, None

    u, v, n = plane_basis(normal, xdir)

    # Project axis direction to 2D
    ad_world = np.array(axis_direction_world, dtype=float)
    ad2 = np.array([ad_world.dot(u), ad_world.dot(v)])
    ad2_norm = float(np.linalg.norm(ad2))
    if ad2_norm < 1e-6:
        # Axis is along the plane normal — no in-plane axis to split on.
        return None, None, None
    ad2 = ad2 / ad2_norm

    # Project mean point to 2D
    mp_world = np.array(mean_point_world, dtype=float)
    rel = mp_world - origin
    mp2 = np.array([rel.dot(u), rel.dot(v)])

    # Project all loops to 2D
    all_pts2 = []
    pts2_per_loop = []
    for loop_3d in loops_3d:
        pts3 = np.array(loop_3d, dtype=float)
        if pts3.shape[0] > 2 and np.allclose(pts3[0], pts3[-1]):
            pts3 = pts3[:-1]
        pts2 = project_points_to_plane(pts3, origin.tolist(), normal, xdir)
        pts2_per_loop.append(pts2)
        all_pts2.append(pts2)
    all_pts2 = np.vstack(all_pts2)

    # Refine the 2D axis using all loop points
    try:
        mp2, ad2, _ = _refine_symmetry_axis_2d(all_pts2, mp2, ad2)
    except Exception as e:
        print(f"  Warning: axis refinement failed ({e}); using analyzer axis")

    # Split each loop. A loop entirely on the *wrong* side of the axis is
    # already the mirror of another loop on the right side — silently skip it
    # instead of bailing on the whole entry. Only bail if NO loop survived.
    new_loops_3d = []
    for pts2 in pts2_per_loop:
        half2 = _split_loop_along_axis_2d(pts2, mp2, ad2)
        if half2 is None or len(half2) < 3:
            continue
        # Unproject to 3D
        half3 = origin[None, :] + half2[:, 0:1] * u[None, :] + half2[:, 1:2] * v[None, :]
        new_loops_3d.append(half3.tolist())
    if not new_loops_3d:
        return None, None, None

    # Reconstruct refined axis in world coords
    refined_mp_world = origin + mp2[0] * u + mp2[1] * v
    refined_ad_world = ad2[0] * u + ad2[1] * v
    refined_ad_world = refined_ad_world / (np.linalg.norm(refined_ad_world) + 1e-12)

    new_entry = copy.deepcopy(entry)
    new_entry['loops_3d'] = new_loops_3d
    new_entry.pop('loops', None)
    return new_entry, refined_mp_world, refined_ad_world


def create_revolve_from_analysis(entry: Dict, revolve_configs: List[Dict], sketch_idx: int) -> List[Dict]:
    """
    Create revolve operations from revolve analysis data.

    For each candidate symmetry axis, split the sketch along the (refined) axis
    and revolve the resulting half-profile by 360°. Skips the candidate if the
    profile cannot be split — a 180° revolve of the full (symmetric) sketch
    relies on OCC to handle self-intersection across the axis and produces a
    degenerate body in practice.
    """
    revolves = []

    # Get plane information for the script
    origin = entry.get('origin', [0, 0, 0])
    normal = entry.get('normal', [0, 0, 1])
    xdir = entry.get('xdir', [1, 0, 0])

    ydir = np.cross(np.array(normal), np.array(xdir))
    rotation_matrix = np.array([xdir, ydir, normal]).T
    inverse_matrix = np.linalg.inv(rotation_matrix)

    for config in revolve_configs:
        mp_world = np.array(config['mean_point'])
        ad_world = np.array(config['axis_direction'])
        ad_world = ad_world / (np.linalg.norm(ad_world) + 1e-12)

        split_entry, refined_mp_world, refined_ad_world = _build_split_entry_for_revolve(
            entry, mp_world, ad_world)

        if split_entry is None:
            print(f"  Sketch {sketch_idx} axis {config.get('axis_idx', '?')}: profile split failed, skipping revolve candidate")
            continue
        insts = build_action_instances_from_entry(split_entry, entry_idx=sketch_idx)
        angle = 360.0
        mp_for_axis = refined_mp_world
        ad_for_axis = refined_ad_world
        split_used = True

        if not insts:
            continue

        # Axis in plane-local coords (existing convention used by the script generator)
        mp_local = inverse_matrix @ mp_for_axis
        ad_local = inverse_matrix @ ad_for_axis
        ad_local = ad_local / (np.linalg.norm(ad_local) + 1e-12)
        axis_start = mp_local
        axis_end = mp_local + ad_local

        revolves.append({
            'type': 'revolve',
            'sketch_idx': sketch_idx,
            'actions': insts,
            'axis_start': axis_start.tolist(),
            'axis_end': axis_end.tolist(),
            'angle': angle,
            'origin': origin,
            'normal': normal,
            'xdir': xdir,
            'axis_idx': config.get('axis_idx', 'unknown'),
            'rotation_type': config.get('rotation_type', 'unknown'),
            'split_profile': split_used,
            # Ranker-only metadata; stripped before serialization/evaluation.
            '_rank': {
                'profile_3d': split_entry.get('loops_3d'),
                'axis_point': np.asarray(mp_for_axis).tolist(),
                'axis_dir': np.asarray(ad_for_axis).tolist(),
            },
        })

    return revolves


def _process_extrusion_worker(args):
    """Worker function for parallel extrusion processing."""
    sketch_idx, entry, translation_analysis_folder = args
    
    def timeout_handler(signum, frame):
        raise TimeoutError("Extrusion processing timed out")
    
    # Per-sketch timeout. Dense slice loops (3000+ pts × many loops) make
    # `segment_greedy_fit` (~O(n²)) take 1-2 min on the worst sketches —
    # we still want to skip truly stuck workers but not drop legitimate ones.
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(300)

    try:
        translation_data = load_translation_analysis(translation_analysis_folder, sketch_idx)

        if translation_data is None:
            signal.alarm(0)  # Cancel the alarm
            return sketch_idx, []

        extrusions = create_extrusion_from_translation(entry, translation_data, sketch_idx)
        signal.alarm(0)  # Cancel the alarm
        return sketch_idx, extrusions
    except TimeoutError:
        signal.alarm(0)  # Cancel the alarm
        print(f"  ⏱️  Sketch {sketch_idx} extrusion processing timed out after 300 seconds")
        return sketch_idx, []
    except Exception as e:
        signal.alarm(0)  # Cancel the alarm
        print(f"  Error processing sketch {sketch_idx} extrusion: {e}")
        return sketch_idx, []


def _process_revolve_worker(args):
    """Worker function for parallel revolve processing."""
    sketch_idx, entry, revolve_analysis_folder = args
    
    def timeout_handler(signum, frame):
        raise TimeoutError("Revolve processing timed out")
    
    # Per-sketch timeout; mirror the extrusion worker's headroom.
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(300)

    try:
        revolve_configs = load_revolve_analysis(revolve_analysis_folder, sketch_idx)

        if not revolve_configs:
            signal.alarm(0)  # Cancel the alarm
            return sketch_idx, []

        revolves = create_revolve_from_analysis(entry, revolve_configs, sketch_idx)
        signal.alarm(0)  # Cancel the alarm
        return sketch_idx, revolves
    except TimeoutError:
        signal.alarm(0)  # Cancel the alarm
        print(f"  ⏱️  Sketch {sketch_idx} revolve processing timed out after 300 seconds")
        return sketch_idx, []
    except Exception as e:
        signal.alarm(0)  # Cancel the alarm
        print(f"  Error processing sketch {sketch_idx} revolve: {e}")
        return sketch_idx, []

def precompute_operations_from_analysis(
    loops_split_path: str,
    loops_split_revolve_path: str,
    translation_analysis_folder: str,
    revolve_analysis_folder: str,
    output_folder: str = "search_precomputed",
    num_workers: int = 8
) -> Dict[str, Any]:
    """
    Load pre-computed analysis results and create operation list.
    
    Args:
        loops_split_path: Path to loops_split.json (for extrusion)
        loops_split_revolve_path: Path to loops_split_revolve.json (for revolve)
        translation_analysis_folder: Folder with translation analysis JSONs
        revolve_analysis_folder: Folder with revolve analysis JSONs
        output_folder: Output folder for results
        num_workers: Number of parallel workers
        
    Returns:
        Dictionary with precomputed operations
    """
    os.makedirs(output_folder, exist_ok=True)
    
    print(f"Loading loops from {loops_split_path}")
    with open(loops_split_path, 'r') as f:
        loops_data = json.load(f)
    
    print(f"Loading revolve loops from {loops_split_revolve_path}")
    with open(loops_split_revolve_path, 'r') as f:
        revolve_data = json.load(f)
    
    all_operations = []
    
    # Process extrusions in parallel
    print(f"\nProcessing extrusions from translation analysis (using {num_workers} workers)...")
    extrusion_count = 0
    
    # Prepare worker arguments
    extrusion_args = [(sketch_idx, entry, translation_analysis_folder) 
                      for sketch_idx, entry in enumerate(loops_data)]
    
    with guarded_pool(num_workers) as pool:
        results, _ = safe_pool_map(pool, _process_extrusion_worker, extrusion_args, stall=900)
    results = [r for r in results if r is not None]
    
    # Collect results
    for sketch_idx, extrusions in results:
        if extrusions:
            all_operations.extend(extrusions)
            extrusion_count += len(extrusions)
            print(f"  Sketch {sketch_idx}: {len(extrusions)} extrusion(s)")
    
    print(f"Total extrusions: {extrusion_count}")
    
    # Process revolves in parallel
    print(f"\nProcessing revolves from revolve analysis (using {num_workers} workers)...")
    revolve_count = 0
    
    # Prepare worker arguments
    revolve_args = [(sketch_idx, entry, revolve_analysis_folder) 
                    for sketch_idx, entry in enumerate(revolve_data)]
    
    with guarded_pool(num_workers) as pool:
        results, _ = safe_pool_map(pool, _process_revolve_worker, revolve_args, stall=900)
    results = [r for r in results if r is not None]
    
    # Collect results
    for sketch_idx, revolves in results:
        if revolves:
            all_operations.extend(revolves)
            revolve_count += len(revolves)
            print(f"  Sketch {sketch_idx}: {len(revolves)} revolve(s)")
    
    print(f"Total revolves: {revolve_count}")

    # Loft / sweep ("generic": self-contained CadQuery code) from analyze_sweep_loft.py.
    generic_count = 0
    generic_path = os.path.join(os.path.dirname(loops_split_path), 'sweep_loft_candidates.json')
    if os.environ.get('CADFIT_SWEEP_LOFT') == '1' and os.path.exists(generic_path):
        with open(generic_path) as f:
            for gi, c in enumerate(json.load(f)):
                all_operations.append({'type': 'generic', 'kind': c['kind'], 'sketch_idx': gi,
                                       'code': c['code'], 'actions': [],
                                       '_rank': None})
                generic_count += 1
        print(f"Total loft/sweep candidates: {generic_count}")
    print(f"Total operations: {len(all_operations)}")

    # Detach ranker-only metadata so the saved/evaluated operations are unchanged.
    rank_meta = [op.pop('_rank', None) for op in all_operations]
    
    # Save precomputed operations
    precomp_data = {
        'operations': all_operations,
        'total_extrusions': extrusion_count,
        'total_revolves': revolve_count,
        'total_operations': len(all_operations)
    }
    
    precomp_path = os.path.join(output_folder, 'precomputed_operations.json')
    with open(precomp_path, 'w') as f:
        json.dump(precomp_data, f, indent=2)
    
    print(f"\nSaved precomputed operations to {precomp_path}")

    precomp_data['rank_meta'] = rank_meta
    return precomp_data


def _evaluate_operation_worker(args):
    """Worker function for parallel operation evaluation with timeout."""
    operation, gt_mesh_path, output_folder, alpha, normalize, points, inside_a = args
    
    def timeout_handler(signum, frame):
        raise TimeoutError("Operation evaluation timed out")
    
    # Per-operation watchdog
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(30)
    
    try:
        result = evaluate_single_operation(
            operation=operation,
            gt_mesh_path=gt_mesh_path,
            output_folder=output_folder,
            alpha=alpha,
            normalize=normalize,
            points=points,
            inside_a=inside_a
        )
        signal.alarm(0)  # Cancel the alarm
        
        if result is not None and result.get('iou', 0.0) >= 0.0005:
            return result
        elif result is not None and os.environ.get('CADFIT_CUT_PHASE') == '1':
            # Near-zero IoU usually means empty space (a hole's own extrusion):
            # useless as an add, but a candidate cut tool.
            result['low_iou'] = True
            return result
        elif result is not None:
            print(f"  Skipping operation with IoU < 0.0005 (IoU = {result.get('iou', 0.0):.6f})")
            return None
        return None
    except TimeoutError:
        signal.alarm(0)  # Cancel the alarm
        print(f"  ⏱️  Operation timed out after 30 seconds, skipping...")
        return None
    except Exception as e:
        signal.alarm(0)  # Cancel the alarm
        print(f"  Error evaluating operation: {e}")
        return None


def evaluate_single_operation(operation: Dict, gt_mesh_path: str, output_folder: str, 
                              alpha: float = 0.01, normalize: bool = True,
                              points=None, inside_a=None) -> Optional[Dict]:
    """
    Evaluate a single operation (extrude or revolve) and compute IoU.
    
    Args:
        operation: Operation dictionary
        gt_mesh_path: Path to ground truth mesh
        output_folder: Output folder
        alpha: Alpha for IoU computation
        normalize: Whether to normalize meshes
        points: Precomputed sample points
        inside_a: Precomputed ground truth inside mask
        
    Returns:
        Dictionary with operation results and IoU, or None if failed
    """
    sketch_idx = operation['sketch_idx']
    op_type = operation['type']
    
    # Create unique filename
    if op_type == 'generic':
        filename = f"generic_{sketch_idx}_{operation['kind']}"
    elif op_type == 'extrude':
        source = operation.get('source', 'unknown')
        filename = f"sketch_{sketch_idx}_{source}"
    else:  # revolve
        axis_idx = operation.get('axis_idx', 'unknown')
        filename = f"sketch_{sketch_idx}_revolve_{axis_idx}"
    
    stl_path = os.path.join(output_folder, f"{filename}.stl")
    script_path = os.path.join(output_folder, f"{filename}.py")
    
    # Generate CadQuery script
    if op_type == 'generic':
        script_content = generate_generic_script(operation['code'], stl_path)
    elif op_type == 'extrude':
        script_content = generate_cadquery_script(
            sketch_actions_list=[operation['actions']],
            height=operation['height'],
            output_stl_path=stl_path
        )
    else:  # revolve
        script_content = generate_cadquery_revolve_script(
            sketch_actions=operation['actions'],
            axis_start=tuple(operation['axis_start']),
            axis_end=tuple(operation['axis_end']),
            angle_degrees=operation['angle'],
            output_stl_path=stl_path,
            origin=operation['origin'],
            normal=operation['normal'],
            xdir=operation['xdir']
        )
    
    # Save and execute script
    with open(script_path, 'w') as f:
        f.write(script_content)
    
    success = execute_cadquery_script(script_content, stl_path, script_path)
    
    if not success or not os.path.exists(stl_path):
        print(f"  Failed to generate {filename}")
        return None
    if op_type == 'generic':
        # Lofts/sweeps can pass OCC's isValid() yet tessellate to an open or
        # self-touching mesh, which would poison every boolean it enters.
        import trimesh as _tm
        _m = _tm.load(stl_path, force='mesh')
        if not (_m.is_watertight and _m.is_winding_consistent and _m.volume > 0):
            print(f"  Rejecting {filename}: tessellation is not a clean volume")
            return None
        # A loft that twists through itself is watertight and consistently
        # wound, but opposite-orientation regions cancel in the volume
        # integral. Its alpha-wrapped hull then has far more volume.
        from iou import _alpha_wrap
        _w = abs(_alpha_wrap(_m).volume)
        if _w > 1.12 * _m.volume:
            print(f"  Rejecting {filename}: self-intersecting (wrapped/mesh volume {_w / _m.volume:.2f})")
            return None
    
    # Compute IoU
    try:
        iou = compute_iou(gt_mesh_path, stl_path, normalize=normalize)
        
        result = operation.copy()
        result['iou'] = iou
        result['stl_path'] = stl_path
        result['script_path'] = script_path
        
        print(f"  {filename}: IoU = {iou:.6f}")
        
        return result
        
    except Exception as e:
        print(f"  Error computing IoU for {filename}: {e}")
        return None


def _cut_pool(results):
    """Every evaluated candidate as a pruning-style group, for the cut phase."""
    pool = []
    for i, r in enumerate(results):
        if r['type'] == 'generic':
            # Loft/sweep solids are fitted to material, not to empty space;
            # as cut tools they only carve plausible-looking damage.
            continue
        tag = {'extrude': 'E', 'revolve': 'R'}.get(r['type'], '?')
        g = {'sketch_idx': r['sketch_idx'], 'sketch_id': f"cut:{tag}{r['sketch_idx']}",
             'individual_iou': r['iou'], 'stl_path': r.get('stl_path'), 'candidate_id': 100000 + i,
             'insts': r.get('actions') or [], 'height': r.get('height', 0)}
        if r['type'] == 'extrude':
            g['type'] = 'pos'
        elif r['type'] == 'revolve':
            g.update(type='revolve', revolve_angle=r['angle'], revolve_axis_start=r['axis_start'],
                     revolve_axis_end=r['axis_end'], revolve_origin=r.get('origin'),
                     revolve_normal=r.get('normal'), revolve_xdir=r.get('xdir'))
        else:
            g.update(type='generic', kind=r['kind'], code=r['code'])
        pool.append(g)
    return pool


def collapse_evaluated_operations(evaluated_operations, fix_sketch_identity=False):
    """Collapse evaluated candidates into the per-sketch dicts that
    `greedy_iou_based_pruning` expects (best extrusion / best revolve per key).

    Stock keys by the int `sketch_idx` even though extrusion and revolve indices
    address different loop files; `fix_sketch_identity` keys by (type, idx).
    """
    # Convert to format expected by greedy_iou_based_pruning
    # The function expects a list of dicts, one per sketch, with fields:
    # insts, pos_h, pos_iou, neg_h, neg_iou, revolve_angle, revolve_iou, etc.
    
    # First, group by sketch_idx
    # IMPORTANT: Store actions separately for each operation since each has different translated origins
    sketches_by_idx = {}
    for result in evaluated_operations:
        if result['type'] == 'generic':
            # Own entry per loft/sweep candidate; positional (stock) keys cannot hold them.
            if not fix_sketch_identity or result['iou'] < 0.0005:
                continue
            key = ('G', result['sketch_idx'])
            sketches_by_idx[key] = {
                'insts': [], 'faces_idx': key, 'sketch_idx': result['sketch_idx'],
                'sketch_id': f"G{result['sketch_idx']}", 'pos_h': None, 'pos_iou': 0.0,
                'neg_h': None, 'neg_iou': 0.0, 'revolve_angle': None, 'revolve_iou': 0.0,
                'pos_actions': None, 'neg_actions': None, 'revolve_actions': None,
                'is_symmetric': False, 'use_revolve': False, 'zero_only': False,
                'generic': {'kind': result['kind'], 'code': result['code'],
                            'iou': result['iou'], 'stl': result.get('stl_path')},
            }
            continue
        is_rev = result['type'] == 'revolve'
        # With the identity fix, extrusions and revolves never share an entry.
        sketch_idx = ('R' if is_rev else 'E', result['sketch_idx']) if fix_sketch_identity else result['sketch_idx']
        if result['iou'] < 0.0005:
            continue
        
        if sketch_idx not in sketches_by_idx:
            sketches_by_idx[sketch_idx] = {
                'insts': result['actions'],  # Will be overwritten with best operation's actions
                'faces_idx': sketch_idx,
                'sketch_idx': result['sketch_idx'],
                'sketch_id': f"{'R' if is_rev else 'E'}{result['sketch_idx']}",
                'pos_h': None,
                'pos_iou': 0.0,
                'pos_actions': None,  # Store actions specific to positive extrusion
                'neg_h': None,
                'neg_iou': 0.0,
                'neg_actions': None,  # Store actions specific to negative extrusion
                'revolve_angle': None,
                'revolve_iou': 0.0,
                'revolve_axis_start': None,
                'revolve_axis_end': None,
                'revolve_actions': None,  # Store actions specific to revolve
                'is_symmetric': False,
                'use_revolve': False,
                'zero_only': True
            }
        
        if result['type'] == 'extrude':
            # Determine if positive or negative based on height
            height = result['height']
            iou_value = result['iou']
            
            if height > 0:
                # Keep the best positive extrusion (allow IoU >= 0)
                if sketches_by_idx[sketch_idx]['pos_h'] is None or sketches_by_idx[sketch_idx]['pos_iou'] < iou_value:
                    sketches_by_idx[sketch_idx]['pos_h'] = height
                    sketches_by_idx[sketch_idx]['pos_iou'] = iou_value
                    sketches_by_idx[sketch_idx]['pos_actions'] = result['actions']  # Store this operation's actions
                    sketches_by_idx[sketch_idx]['pos_stl'] = result.get('stl_path')
                    sketches_by_idx[sketch_idx]['zero_only'] = False
            else:
                # Keep the best negative extrusion (allow IoU >= 0)
                if sketches_by_idx[sketch_idx]['neg_h'] is None or sketches_by_idx[sketch_idx]['neg_iou'] < iou_value:
                    sketches_by_idx[sketch_idx]['neg_h'] = abs(height)
                    sketches_by_idx[sketch_idx]['neg_iou'] = iou_value
                    sketches_by_idx[sketch_idx]['neg_actions'] = result['actions']  # Store this operation's actions
                    sketches_by_idx[sketch_idx]['zero_only'] = False
        
        else:  # revolve
            iou_value = result['iou']
            # Keep the best revolve operation (allow IoU >= 0)
            if sketches_by_idx[sketch_idx]['revolve_angle'] is None or sketches_by_idx[sketch_idx]['revolve_iou'] < iou_value:
                sketches_by_idx[sketch_idx]['revolve_angle'] = result['angle']
                sketches_by_idx[sketch_idx]['revolve_iou'] = iou_value
                sketches_by_idx[sketch_idx]['revolve_axis_start'] = result['axis_start']
                sketches_by_idx[sketch_idx]['revolve_axis_end'] = result['axis_end']
                sketches_by_idx[sketch_idx]['revolve_actions'] = result['actions']  # Store this operation's actions
                sketches_by_idx[sketch_idx]['revolve_stl'] = result.get('stl_path')
                if fix_sketch_identity:
                    # Frame the revolve was evaluated in; pruning rebuilds it identically.
                    sketches_by_idx[sketch_idx]['revolve_origin'] = result.get('origin')
                    sketches_by_idx[sketch_idx]['revolve_normal'] = result.get('normal')
                    sketches_by_idx[sketch_idx]['revolve_xdir'] = result.get('xdir')
                sketches_by_idx[sketch_idx]['is_symmetric'] = True
                sketches_by_idx[sketch_idx]['zero_only'] = False
                
                # Use revolve if it's better than extrusions
                best_extrude_iou = max(
                    sketches_by_idx[sketch_idx]['pos_iou'],
                    sketches_by_idx[sketch_idx]['neg_iou']
                )
                if iou_value > best_extrude_iou:
                    sketches_by_idx[sketch_idx]['use_revolve'] = True
    
    # Now determine which actions to use based on best operation
    for sketch_idx, sketch_data in sketches_by_idx.items():
        if sketch_data['use_revolve'] and sketch_data['revolve_actions'] is not None:
            sketch_data['insts'] = sketch_data['revolve_actions']
            # Stock: the extrusion candidate will be rebuilt from these (revolve)
            # actions, so its evaluated STL no longer describes it. With the
            # identity fix each entry holds one type, so the STL stays valid.
            if not fix_sketch_identity:
                sketch_data['pos_stl'] = None
        elif sketch_data['pos_iou'] >= sketch_data['neg_iou'] and sketch_data['pos_actions'] is not None:
            sketch_data['insts'] = sketch_data['pos_actions']
            if not fix_sketch_identity:
                sketch_data['revolve_stl'] = None
        elif sketch_data['neg_actions'] is not None:
            sketch_data['insts'] = sketch_data['neg_actions']
        # If all are None, keep the default empty actions
    
    # Convert to list (sorted by sketch_idx)
    precomp_for_greedy = []
    if fix_sketch_identity:
        # One entry per (type, sketch); no positional dummies needed.
        precomp_for_greedy = [sketches_by_idx[k] for k in sorted(sketches_by_idx)]
    max_sketch_idx = max(sketches_by_idx.keys()) if sketches_by_idx and not fix_sketch_identity else -1
    
    for idx in range(max_sketch_idx + 1):
        if idx in sketches_by_idx:
            precomp_for_greedy.append(sketches_by_idx[idx])
        else:
            # Add dummy entry for missing sketches
            precomp_for_greedy.append({
                'insts': [],
                'faces_idx': idx,
                'pos_h': None,
                'pos_iou': 0.0,
                'neg_h': None,
                'neg_iou': 0.0,
                'revolve_angle': None,
                'revolve_iou': 0.0,
                'revolve_axis_start': None,
                'revolve_axis_end': None,
                'is_symmetric': False,
                'use_revolve': False,
                'zero_only': True
            })
    
    return precomp_for_greedy


def run_greedy_search(
    loops_split_path: str,
    loops_split_revolve_path: str,
    ground_truth_path: str,
    translation_analysis_folder: str,
    revolve_analysis_folder: str,
    output_folder: str = "search_precomputed",
    alpha: float = 0.01,
    normalize: bool = True,
    num_workers: int = 8,
    candidate_ranking: bool = False,
    candidate_per_group: int = 1,
    candidate_top_k: Optional[int] = None,
    candidate_keep_ratio: Optional[float] = None,
    candidate_drop_tau: Optional[float] = None,
    fast_prune: bool = False,
    fix_sketch_identity: bool = False,
    fix_iou_validity: bool = False,
    cache_volumes: bool = False,
    persistent_pool: bool = False,
    cache_solids: bool = False,
):
    """
    Run CAD reconstruction using pre-computed analysis results.
    
    Args:
        loops_split_path: Path to loops_split.json
        loops_split_revolve_path: Path to loops_split_revolve.json
        ground_truth_path: Path to ground truth STL
        translation_analysis_folder: Folder with translation analysis
        revolve_analysis_folder: Folder with revolve analysis
        output_folder: Output folder
        alpha: Alpha for IoU computation
        normalize: Whether to normalize meshes
        num_workers: Number of parallel workers
        candidate_ranking: CADFit++ — rank candidates with a kernel-free proxy
            IoU and only evaluate the retained ones (see candidate_ranker.py)
        candidate_per_group: candidates kept per (type, sketch) group
        candidate_top_k / candidate_keep_ratio: optional global budget
        candidate_drop_tau: drop whole groups whose best proxy IoU is below this
        fast_prune: output-preserving speedups inside greedy pruning
        fix_sketch_identity: keep extrusion and revolve candidates apart. Their
            `sketch_idx` values index different loop files, and stock CADFit merges
            them under one int and rebuilds the loser from the winner's sketch.
    """
    os.makedirs(output_folder, exist_ok=True)
    if fix_iou_validity:
        # Read by iou.py in this process and in every pool worker.
        os.environ["CADFIT_IOU_VALIDATE"] = "1"
    
    # Step 1: Load pre-computed operations
    print("="*80)
    print("STEP 1: Loading pre-computed operations")
    print("="*80)
    
    precomp_data = precompute_operations_from_analysis(
        loops_split_path=loops_split_path,
        loops_split_revolve_path=loops_split_revolve_path,
        translation_analysis_folder=translation_analysis_folder,
        revolve_analysis_folder=revolve_analysis_folder,
        output_folder=output_folder,
        num_workers=num_workers
    )
    
    operations = precomp_data['operations']
    
    if not operations:
        print("No valid operations found! Writing IoU=0 result.")
        final_iou_path = os.path.join(output_folder, 'final_iou.json')
        with open(final_iou_path, 'w') as f:
            json.dump({"iou": 0.0, "note": "no valid operations"}, f, indent=2)
        return
    
    # Step 2: Evaluate all operations
    print("\n" + "="*80)
    print("STEP 2: Evaluating all operations")
    print("="*80)
    
    # Load ground truth mesh for IoU computation
    print(f"Loading ground truth: {ground_truth_path}")
    gt_mesh = trimesh.load(ground_truth_path, force='mesh')
    
    if normalize:
        gt_mesh = normalize_mesh(gt_mesh)
    
    # CPU boolean IoU does not need sample-point precomputation
    inside_gt, points = None, None

    # CADFit++: cheap candidate ranking before kernel evaluation
    ranking_rows = None
    if candidate_ranking:
        import time as _time
        from candidate_ranker import build_context, rank_candidates
        _t0 = _time.time()
        original_count = len(operations)
        ctx = build_context(gt_mesh)
        all_operations = operations
        operations, ranking_rows = rank_candidates(
            all_operations, precomp_data['rank_meta'], ctx,
            per_group_m=candidate_per_group, top_k=candidate_top_k,
            keep_ratio=candidate_keep_ratio, drop_tau=candidate_drop_tau,
        )
        print(f"CADFit++ ranking: {original_count} -> {len(operations)} candidates "
              f"({_time.time() - _t0:.1f}s)")
        log_event("ranking", duration=_time.time() - _t0, n_in=original_count, n_out=len(operations))
    
    # Evaluate each operation in parallel
    print(f"\nEvaluating operations in parallel (using {num_workers} workers)...")
    
    # Prepare worker arguments
    eval_args = [(operation, ground_truth_path, output_folder, alpha, normalize, points, inside_gt) 
                 for operation in operations]
    
    # Was previously capped at 8 to avoid GPU contention during IoU sampling.
    # IoU is fully CPU now, so let it scale with the requested worker count.
    import time as _time
    _t_eval = _time.time()
    from iou import warm_manifold
    warm_manifold(ground_truth_path, normalize)
    with guarded_pool(max(1, num_workers), initializer=warm_manifold,
                 initargs=(ground_truth_path, normalize)) as pool:
        results, _ = safe_pool_map(pool, _evaluate_operation_worker, eval_args, stall=900)
    
    # Filter out None results
    evaluated_operations = [r for r in results if r is not None and not r.get('low_iou')]
    cut_pool = _cut_pool([r for r in results if r is not None]) if os.environ.get('CADFIT_CUT_PHASE') == '1' else None
    log_event("evaluate", duration=_time.time() - _t_eval, n=len(operations), n_ok=len(evaluated_operations))

    if ranking_rows is not None:
        # Record what happened to every candidate, including the ones that were
        # never evaluated or that evaluation discarded (failed/timeout/IoU floor).
        evaluated_iter = iter(results)
        for row in ranking_rows:
            if not row['retained']:
                row.update(status='not_evaluated', true_iou=None)
                continue
            r = next(evaluated_iter)
            row.update(status='ok' if r is not None else 'discarded',
                       true_iou=None if r is None else r.get('iou'))
        with open(os.path.join(output_folder, 'candidate_ranking.json'), 'w') as f:
            json.dump(ranking_rows, f, indent=2)
    
    print(f"\nSuccessfully evaluated {len(evaluated_operations)}/{len(operations)} operations (filtered IoU >= 0.0005)")
    
    # Save evaluated operations
    eval_path = os.path.join(output_folder, 'evaluated_operations.json')
    with open(eval_path, 'w') as f:
        json.dump(evaluated_operations, f, indent=2)
    print(f"Saved evaluated operations to {eval_path}")
    
    if not evaluated_operations:
        print("\nNo valid operations after evaluation! Writing IoU=0 result.")
        final_iou_path = os.path.join(output_folder, 'final_iou.json')
        with open(final_iou_path, 'w') as f:
            json.dump({"iou": 0.0, "note": "no valid operations"}, f, indent=2)
        return
    
    # Early stop: if any single operation already has IoU > 0.99, use it directly
    best_single = max(evaluated_operations, key=lambda r: r.get('iou', 0.0))
    if best_single.get('iou', 0.0) > 0.99:
        print(f"\n✓ Single operation already has IoU {best_single['iou']:.6f} > 0.99, skipping greedy search")
        import shutil, subprocess
        final_stl_path = os.path.join(output_folder, 'best_greedy_parallel.stl')
        if best_single.get('stl_path') and os.path.exists(best_single['stl_path']):
            shutil.copy2(best_single['stl_path'], final_stl_path)
        if best_single.get('script_path') and os.path.exists(best_single['script_path']):
            shutil.copy2(best_single['script_path'], os.path.join(output_folder, 'best_greedy_parallel.py'))
        print(f"\n{'='*80}")
        print("DONE!")
        print(f"Final IoU: {best_single['iou']:.6f}")
        print(f"{'='*80}")
        return
    
    # Step 3: Run greedy IoU-based pruning
    print("\n" + "="*80)
    print("STEP 3: Running greedy IoU-based pruning")
    print("="*80)
    
    precomp_for_greedy = collapse_evaluated_operations(evaluated_operations, fix_sketch_identity)

    def _prune(precomp, order):
        # greedy_iou_based_pruning resumes from these files if present.
        for f in ('greedy_instruction_groups.pkl', 'greedy_keep_mask.json',
                  'greedy_extrusion_data.json', 'greedy_final_actions.pkl'):
            try:
                os.remove(os.path.join(output_folder, f))
            except OSError:
                pass
        return greedy_iou_based_pruning(
            precomp=precomp,
            gt_mesh=gt_mesh,
            output_folder=output_folder,
            alpha=alpha,
            num_workers=num_workers,
            fast_prune=fast_prune,
            cache_volumes=cache_volumes,
            persistent_pool=persistent_pool,
            cache_solids=cache_solids,
            cut_pool=cut_pool,
            order=order,
        )

    if os.environ.get('CADFIT_MULTISTART') == '1' and os.environ.get('CADFIT_EXACT_UNION') == '1':
        # Multi-start: the greedy is myopic, so a larger candidate pool can
        # steer it into a worse local optimum. Try several forward orders and
        # the pool without loft/sweep, keep the best by exact IoU, and run the
        # winner last so the files on disk belong to it.
        no_generic = [e for e in precomp_for_greedy if not e.get('generic')]
        variants = [('ratio', precomp_for_greedy), ('iou', precomp_for_greedy), ('volume', precomp_for_greedy)]
        if len(no_generic) < len(precomp_for_greedy):
            variants.append(('ratio', no_generic))
        results = []
        for order, pc in variants:
            res = _prune(pc, order)
            label = f"{order}{'' if pc is precomp_for_greedy else '/no-generic'}"
            print(f"  Multi-start variant {label}: IoU {res[0]:.6f}")
            log_event("multistart", variant=label, iou=float(res[0]))
            results.append(res)
        best = int(max(range(len(results)), key=lambda i: results[i][0]))
        if best == len(variants) - 1:
            final_iou, final_mesh, final_actions = results[best]
        else:
            final_iou, final_mesh, final_actions = _prune(variants[best][1], variants[best][0])
    else:
        final_iou, final_mesh, final_actions = _prune(precomp_for_greedy, 'ratio')
    
    # `greedy_tmp.stl` was built via manifold3d's robust union on each
    # candidate's STL and is clean + watertight — use that as the canonical
    # final STL. The saved `best_greedy_parallel.py` script is for human
    # inspection only (no exporter line); we don't execute it.
    best_greedy_script = os.path.join(output_folder, 'best_greedy_parallel.py')
    final_stl_path = os.path.join(output_folder, 'best_greedy_parallel.stl')
    import shutil as _shutil
    greedy_tmp = os.path.join(output_folder, 'greedy_tmp.stl')
    if os.path.exists(greedy_tmp):
        try:
            _shutil.copy2(greedy_tmp, final_stl_path)
            print(f"✓ Replaced {os.path.basename(final_stl_path)} with manifold3d-built greedy_tmp.stl")
        except Exception as e:
            print(f"⚠️  Could not copy greedy_tmp.stl over final STL: {e}")
    
    # The IoU returned by greedy_iou_based_pruning is for `greedy_tmp.stl`,
    # built via manifold3d unions on alpha-wrapped meshes. The rebuilt
    # `best_greedy_parallel.stl` uses CadQuery (OCC) `.union()`, which can
    # produce different geometry — so re-measure on the file that will
    # actually flow downstream.
    from iou import mesh_iou_cpu_boolean as _iou_cpu
    if os.path.exists(final_stl_path):
        try:
            rebuilt_iou = _iou_cpu(ground_truth_path, final_stl_path, normalize=True, verbose=False)
            print(f"\nRebuilt best_greedy_parallel.stl IoU vs GT: {rebuilt_iou:.6f}  (vs greedy_tmp {final_iou:.6f})")
            final_iou = rebuilt_iou
        except Exception as e:
            print(f"⚠️  Could not re-measure rebuilt IoU: {e}")

    # If any individual candidate beats the rebuilt mesh, swap.
    best_single = max(evaluated_operations, key=lambda r: r.get('iou', 0.0)) if evaluated_operations else {'iou': 0.0}
    if best_single.get('iou', 0.0) > final_iou:
        print(f"\n⚠️  Greedy IoU ({final_iou:.6f}) < best individual IoU ({best_single['iou']:.6f}), using individual instead")
        import shutil
        if best_single.get('stl_path') and os.path.exists(best_single['stl_path']):
            shutil.copy2(best_single['stl_path'], final_stl_path)
        if best_single.get('script_path') and os.path.exists(best_single['script_path']):
            shutil.copy2(best_single['script_path'], best_greedy_script)
        final_iou = best_single['iou']
    
    print("\n" + "="*80)
    print("DONE!")
    print(f"Final IoU: {final_iou:.6f}")
    print("="*80)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CAD reconstruction using pre-computed analysis')
    parser.add_argument('loops_split', help='Path to loops_split.json')
    parser.add_argument('loops_split_revolve', help='Path to loops_split_revolve.json')
    parser.add_argument('ground_truth', help='Path to ground truth STL')
    parser.add_argument('translation_analysis', help='Folder with translation analysis JSONs')
    parser.add_argument('revolve_analysis', help='Folder with revolve analysis JSONs')
    parser.add_argument('--output-folder', default='search_precomputed', help='Output folder')
    parser.add_argument('--alpha', type=float, default=0.01, help='Alpha for IoU computation')
    parser.add_argument('--normalize', action='store_true', help='Normalize meshes')
    parser.add_argument('--num-workers', type=int, default=20, help='Number of parallel workers')
    parser.add_argument('--candidate-ranking', action='store_true',
                        help='CADFit++: rank candidates with a proxy IoU and evaluate only the retained ones')
    parser.add_argument('--candidate-per-group', type=int, default=1,
                        help='Candidates kept per (type, sketch) group (default: 1)')
    parser.add_argument('--candidate-top-k', type=int, default=None, help='Optional global candidate budget')
    parser.add_argument('--candidate-keep-ratio', type=float, default=None,
                        help='Optional global candidate budget as a fraction of all candidates')
    parser.add_argument('--candidate-drop-tau', type=float, default=None,
                        help='Drop whole groups whose best proxy IoU is below this value')
    parser.add_argument('--fast-prune', action='store_true',
                        help='Output-preserving speedups inside greedy pruning')
    parser.add_argument('--cache-volumes', action=argparse.BooleanOptionalAction, default=True,
                        help='Read candidate volumes from the STLs built during evaluation (part of --fast-prune)')
    parser.add_argument('--persistent-pool', action=argparse.BooleanOptionalAction, default=True,
                        help='Reuse one worker pool across removal iterations (part of --fast-prune)')
    parser.add_argument('--cache-solids', action=argparse.BooleanOptionalAction, default=True,
                        help='Build pruning subsets by concatenating the candidate STLs from evaluation '
                             'instead of re-running CadQuery (requires --fix-sketch-identity)')
    parser.add_argument('--fix-iou-validity', action=argparse.BooleanOptionalAction, default=True,
                        help='Only trust direct manifold conversion for genuine volumes; alpha-wrap otherwise '
                             '(stock can return IoU > 1 on self-overlapping compounds)')
    parser.add_argument('--fix-sketch-identity', action=argparse.BooleanOptionalAction, default=True,
                        help='Keep extrusion and revolve candidates apart in pruning (stock merges '
                             'them by int index and rebuilds the loser from the winner\'s sketch)')
    
    args = parser.parse_args()
    # `kill -USR1 <pid>` appends every thread's stack to stack_dump.txt: the
    # step has hung past its budgets on raw ABC parts, and ptrace (py-spy) is
    # not always allowed. A file, because a timed-out step loses its stderr.
    import faulthandler
    os.makedirs(args.output_folder, exist_ok=True)
    _dump_file = open(os.path.join(args.output_folder, 'stack_dump.txt'), 'a')
    faulthandler.register(signal.SIGUSR1, file=_dump_file, all_threads=True)
    if args.cache_solids and not args.fix_sketch_identity:
        parser.error('--cache-solids requires --fix-sketch-identity (stock rebuilds losers from the winner\'s sketch, '
                     'so the evaluated STL would not match)')
    
    run_greedy_search(
        loops_split_path=args.loops_split,
        loops_split_revolve_path=args.loops_split_revolve,
        ground_truth_path=args.ground_truth,
        translation_analysis_folder=args.translation_analysis,
        revolve_analysis_folder=args.revolve_analysis,
        output_folder=args.output_folder,
        alpha=args.alpha,
        normalize=args.normalize,
        num_workers=args.num_workers,
        candidate_ranking=args.candidate_ranking,
        candidate_per_group=args.candidate_per_group,
        candidate_top_k=args.candidate_top_k,
        candidate_keep_ratio=args.candidate_keep_ratio,
        candidate_drop_tau=args.candidate_drop_tau,
        fast_prune=args.fast_prune,
        fix_sketch_identity=args.fix_sketch_identity,
        fix_iou_validity=args.fix_iou_validity,
        cache_volumes=args.cache_volumes,
        persistent_pool=args.persistent_pool,
        cache_solids=args.cache_solids,
    )

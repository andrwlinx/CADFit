#!/usr/bin/env python3
"""CadQuery operation evaluation and greedy IoU-based pruning.

Each candidate operation (extrusion or revolve) is materialized via CadQuery,
its IoU against the ground-truth mesh is computed with CPU mesh booleans,
and a greedy pass keeps the subset that maximizes union IoU.
"""
from __future__ import annotations

import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"

import argparse
import builtins as _builtins
import json
import pickle
import glob
import time
import signal
import subprocess
import tempfile
import contextlib
import multiprocessing as mp
from typing import List, Dict, Any, Optional, Tuple
import tqdm
import numpy as np
import trimesh
import matplotlib
from profiling import log_event
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from fit_primitives import build_action_instances_from_entry

from iou import mesh_iou_cpu_boolean, normalize_mesh


def project_3d_to_2d(points_3d, origin, normal, xdir):
    """
    Project 3D points onto a 2D plane coordinate system.
    
    Args:
        points_3d: Nx3 array of 3D points
        origin: Origin of the plane
        normal: Normal vector of the plane
        xdir: X-direction vector of the plane
        
    Returns:
        Nx2 array of 2D points
    """
    points_3d = np.array(points_3d)
    origin = np.array(origin)
    normal = np.array(normal)
    xdir = np.array(xdir)
    
    # Normalize vectors
    normal = normal / np.linalg.norm(normal)
    xdir = xdir / np.linalg.norm(xdir)
    
    # Compute y-direction (perpendicular to both normal and xdir)
    ydir = np.cross(normal, xdir)
    ydir = ydir / np.linalg.norm(ydir)
    
    # Project points onto plane
    points_2d = []
    for point in points_3d:
        relative = point - origin
        x = np.dot(relative, xdir)
        y = np.dot(relative, ydir)
        points_2d.append([x, y])
    
    return np.array(points_2d)


def check_symmetry_axis(points_2d, axis_angle_deg, tolerance=0.03):
    """
    Check if 2D points are symmetric about an axis through their centroid.
    
    Args:
        points_2d: Nx2 array of 2D points
        axis_angle_deg: Angle of axis in degrees (0 = x-axis)
        tolerance: Distance tolerance for symmetry (as fraction of point cloud size)
        
    Returns:
        (is_symmetric, axis_unit_vector, symmetry_ratio)
    """
    if len(points_2d) < 4:
        return False, None, 0.0
    
    # Compute centroid
    centroid = np.mean(points_2d, axis=0)
    centered = points_2d - centroid

    # Check if points form a circle - skip symmetry check for circles
    # A circle has uniform distance from centroid
    distances_from_centroid = np.linalg.norm(centered, axis=1)

    if np.allclose(distances_from_centroid, distances_from_centroid[0], rtol=0.01):
        # This is likely a circle, skip symmetry axis check
        return False, None, 0.0
    
    # Axis direction
    axis_rad = np.radians(axis_angle_deg)
    axis_dir = np.array([np.cos(axis_rad), np.sin(axis_rad)])
    
    # Perpendicular to axis
    perp_dir = np.array([-np.sin(axis_rad), np.cos(axis_rad)])
    
    # Project points onto perpendicular direction (distance from axis)
    perp_distances = centered @ perp_dir
    
    # Flip points across axis
    flipped_centered = centered - 2 * np.outer(perp_distances, perp_dir)
    flipped = flipped_centered + centroid
    
    # Check if flipped points match original points
    # For each flipped point, find closest original point
    from scipy.spatial.distance import cdist
    distances = cdist(flipped, points_2d)
    min_distances = np.min(distances, axis=1)
    
    # Compute characteristic size
    bbox_size = np.max(np.ptp(points_2d, axis=0))
    threshold = tolerance * bbox_size
    
    # Check if most points have a close match
    symmetric_points = np.sum(min_distances < threshold)
    symmetry_ratio = symmetric_points / len(points_2d)
    
    is_symmetric = symmetry_ratio > 0.95  # 95% of points should match
    
    return is_symmetric, axis_dir, symmetry_ratio


def plot_symmetry_2d(loops_2d, sketch_idx, axis_angle_deg, axis_dir_2d, symmetry_ratio, output_folder):
    """
    Plot 2D sketch with symmetry axis.
    
    Args:
        loops_2d: List of 2D loops (each loop is Nx2 array)
        sketch_idx: Sketch index
        axis_angle_deg: Angle of symmetry axis in degrees
        axis_dir_2d: 2D direction vector of axis
        symmetry_ratio: Symmetry match ratio
        output_folder: Output folder for plots
    """
    try:
        import matplotlib.pyplot as plt
        
        os.makedirs(f'{output_folder}/symmetry_plots', exist_ok=True)
        
        fig, ax = plt.subplots(figsize=(10, 10))
        
        # Plot all loops
        all_points = []
        for i, loop in enumerate(loops_2d):
            loop_array = np.array(loop)
            all_points.extend(loop)
            
            # Plot loop
            ax.plot(loop_array[:, 0], loop_array[:, 1], 'b-', linewidth=2, label=f'Loop {i}' if i < 3 else '')
            
            # Mark start point
            ax.plot(loop_array[0, 0], loop_array[0, 1], 'go', markersize=8)
        
        all_points = np.array(all_points)
        
        # Compute centroid and extent for axis
        centroid = np.mean(all_points, axis=0)
        bbox_range = np.max(np.ptp(all_points, axis=0))
        extent = bbox_range * 0.7
        
        # Plot symmetry axis
        axis_start = centroid - extent * axis_dir_2d
        axis_end = centroid + extent * axis_dir_2d
        
        ax.plot([axis_start[0], axis_end[0]], [axis_start[1], axis_end[1]], 
               'r--', linewidth=3, alpha=1.0, label=f'Symmetry Axis {axis_angle_deg}° (ratio={symmetry_ratio:.2%})')
        
        # Plot centroid
        ax.plot(centroid[0], centroid[1], 'r*', markersize=15, label='Centroid', zorder=10)
        
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.set_title(f'Sketch {sketch_idx} - SYMMETRIC (axis={axis_angle_deg}°, ratio={symmetry_ratio:.2%})')
        ax.grid(True, alpha=0.3)
        ax.axis('equal')
        ax.legend(loc='best', fontsize=10)
        
        plt.tight_layout()
        output_path = f'{output_folder}/symmetry_plots/sketch_{sketch_idx}_symmetric_{axis_angle_deg}deg.png'
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        print(f"  Saved symmetry plot: {output_path}")
        
    except Exception as e:
        print(f"  Failed to save symmetry plot: {e}")


def find_symmetry_axis(entry, sketch_idx=None, output_folder=None):
    """
    Find axis of symmetry for a sketch by testing 4 axes (0°, 45°, 90°, 135°).
    Projects 3D loops to 2D before testing.
    Returns ALL symmetric axes found, not just the first one.
    
    Args:
        entry: Sketch entry with loops_3d or loops
        sketch_idx: Sketch index (for plotting)
        output_folder: Output folder (for plotting)
        
    Returns:
        List of dicts with 'angle', 'ratio', 'axis_3d_start', 'axis_3d_end' for each symmetric axis,
        or empty list if no symmetry found
    """
    # Get 3D loops
    loops_3d = entry.get('loops_3d', entry.get('loops', []))
    
    if not loops_3d:
        return []
    
    # Get plane information
    origin = entry.get('origin', [0, 0, 0])
    normal = entry.get('normal', [0, 0, 1])
    xdir = entry.get('xdir', [1, 0, 0])
    
    # Project 3D loops to 2D
    all_points_2d = []
    loops_2d = []
    for loop_3d in loops_3d:
        loop_2d = project_3d_to_2d(loop_3d, origin, normal, xdir)
        all_points_2d.extend(loop_2d)
        loops_2d.append(loop_2d)
    
    if len(all_points_2d) < 4:
        return []
    
    all_points_2d = np.array(all_points_2d)
    
    # Remove duplicates
    unique_points = np.unique(all_points_2d, axis=0)
    
    # Compute principal axes using PCA
    centered_points = unique_points - np.mean(unique_points, axis=0)
    cov_matrix = np.cov(centered_points.T)
    eigenvalues, eigenvectors = np.linalg.eig(cov_matrix)
    
    # Sort by eigenvalue (descending)
    sorted_indices = np.argsort(eigenvalues)[::-1]
    principal_axes = eigenvectors[:, sorted_indices]
    
    # Convert principal axes to angles (in degrees)
    pca_angles = []
    for i in range(2):  # First two principal axes
        axis_vec = principal_axes[:, i]
        angle_rad = np.arctan2(axis_vec[1], axis_vec[0])
        angle_deg = np.degrees(angle_rad) % 180  # Normalize to [0, 180)
        pca_angles.append(angle_deg)
    
    # Test 4 fixed axes plus 2 PCA axes and collect ALL symmetric ones
    test_angles = [0, 45, 90, 135] + pca_angles
    symmetric_axes = []
    symmetric_axes_2d = []
    
    for angle in test_angles:
        is_sym, axis_dir_2d, ratio = check_symmetry_axis(unique_points, angle, tolerance=0.05)
        
        if is_sym:
            symmetric_axes_2d.append({
                'angle': int(angle),
                'axis_dir_2d': axis_dir_2d,
                'ratio': float(ratio)
            })
    
    if not symmetric_axes_2d:
        return []
    
    # Convert all symmetric axes to 3D
    origin_arr = np.array(origin)
    normal_arr = np.array(normal)
    xdir_arr = np.array(xdir)
    
    # Normalize vectors
    normal_arr = normal_arr / np.linalg.norm(normal_arr)
    xdir_arr = xdir_arr / np.linalg.norm(xdir_arr)
    
    # Compute y-direction (perpendicular to both normal and xdir)
    ydir_arr = np.cross(normal_arr, xdir_arr)
    ydir_arr = ydir_arr / np.linalg.norm(ydir_arr)
    
    # Centroid in 2D
    centroid_2d = np.mean(unique_points, axis=0)
    
    # Centroid in 3D (fixed: swap xdir and ydir components)
    centroid_3d = origin_arr + centroid_2d[0] * ydir_arr + centroid_2d[1] * xdir_arr
    
    # Convert each symmetric axis to 3D
    for sym_axis in symmetric_axes_2d:
        axis_dir_2d = sym_axis['axis_dir_2d']
        angle = sym_axis['angle']
        ratio = sym_axis['ratio']
        
        print(f"  Found symmetry at {angle}° axis (ratio={ratio:.2%})")
        
        # Save plot if requested (plot for first/best axis)
        if sketch_idx is not None and output_folder is not None and len(symmetric_axes) == 0:
            plot_symmetry_2d(loops_2d, sketch_idx, angle, axis_dir_2d, ratio, output_folder)
        
        # Convert axis direction to 3D (fixed: swap xdir and ydir components)
        axis_3d_dir = axis_dir_2d[0] * ydir_arr + axis_dir_2d[1] * xdir_arr
        axis_3d_dir = axis_3d_dir / np.linalg.norm(axis_3d_dir)
        
        # Axis endpoints (extend 10 units in each direction)
        axis_3d_start = tuple(centroid_3d - 10 * axis_3d_dir)
        axis_3d_end = tuple(centroid_3d + 10 * axis_3d_dir)
        
        symmetric_axes.append({
            'angle': angle,
            'ratio': ratio,
            'axis_3d_start': axis_3d_start,
            'axis_3d_end': axis_3d_end
        })
    
    return symmetric_axes


def cut_loop_at_symmetry_axis(loop_2d, axis_angle_deg):
    """
    Cut a 2D loop along a symmetry axis and close it with a line segment.
    Removes ALL points on the negative side of the axis.
    
    Args:
        loop_2d: List of [x, y] points forming a closed loop
        axis_angle_deg: Angle of symmetry axis in degrees
        
    Returns:
        Modified loop with cut and closure
    """
    points = np.array(loop_2d)
    
    # Remove closing duplicate if present
    if len(points) > 0 and np.allclose(points[0], points[-1]):
        points = points[:-1]
    
    if len(points) < 3:
        return loop_2d
    
    # Centroid
    centroid = np.mean(points, axis=0)
    
    # Axis direction
    axis_rad = np.radians(axis_angle_deg)
    axis_dir = np.array([np.cos(axis_rad), np.sin(axis_rad)])
    perp_dir = np.array([-np.sin(axis_rad), np.cos(axis_rad)])
    
    # Project points onto perpendicular direction
    centered = points - centroid
    perp_distances = centered @ perp_dir
    
    # Find points on or near the axis (within small threshold)
    threshold = 0.01 * np.max(np.abs(perp_distances))
    on_axis = np.abs(perp_distances) < threshold
    
    # Keep only points on positive side OR on axis (remove ALL negative side points)
    positive_side = perp_distances >= -threshold  # Changed to >= to keep axis and positive side only
    
    if not np.any(positive_side):
        # All points on negative side, return empty
        return []
    
    # Keep only points on positive side and points on axis
    keep_mask = positive_side
    cut_points = points[keep_mask]
    
    if len(cut_points) < 2:
        return []
    
    # Add closing line segment if needed
    if not np.allclose(cut_points[0], cut_points[-1]):
        cut_points = np.vstack([cut_points, cut_points[0]])
    
    return cut_points.tolist()


def generate_cadquery_revolve_script(sketch_actions: List[str], axis_start: Tuple[float, float, float], 
                                     axis_end: Tuple[float, float, float], angle_degrees: float, 
                                     output_stl_path: str, origin=None, normal=None, xdir=None) -> str:
    """
    Generate CadQuery script for revolve operation.
    
    Args:
        sketch_actions: List of sketch action strings
        axis_start: (x, y, z) start point of revolution axis
        axis_end: (x, y, z) end point of revolution axis
        angle_degrees: Angle to revolve in degrees
        output_stl_path: Path to save output STL
        origin: 3D origin of the plane (optional, if None will use existing plane definition)
        normal: 3D normal vector of the plane (optional)
        xdir: 3D x-direction of the plane (optional)
        
    Returns:
        Python script content
    """
    script_lines = ["import cadquery as cq", "import math", ""]
    
    plane_name = "plane_1"
    sketch_name = "sketch_1"
    
    # Use plane information from arguments if provided
    if origin is not None and normal is not None and xdir is not None:
        script_lines.append(f"# Plane definition from JSON")
        script_lines.append(f"origin = ({round(origin[0], 3)}, {round(origin[1], 3)}, {round(origin[2], 3)})")
        script_lines.append(f"normal = ({round(normal[0], 3)}, {round(normal[1], 3)}, {round(normal[2], 3)})")
        script_lines.append(f"xdir = ({round(xdir[0], 3)}, {round(xdir[1], 3)}, {round(xdir[2], 3)})")
        script_lines.append(f"{plane_name} = cq.Plane(origin=origin, normal=normal, xDir=xdir)")
        script_lines.append(f"{sketch_name} = cq.Workplane({plane_name})")
        script_lines.append("")
    else:
        # Find plane definition from sketch actions
        plane_def_line = None
        workplane_def_line = None
        
        for action in sketch_actions:
            action_lines = action.split('\n')
            for line in action_lines:
                line = line.strip()
                if line.startswith("plane = "):
                    plane_def_line = line.replace("plane = ", f"{plane_name} = ")
                elif line.startswith("sketch = cq.Workplane("):
                    if "cq.Workplane(plane)" in line:
                        workplane_def_line = f"{sketch_name} = cq.Workplane({plane_name})"
                    else:
                        workplane_def_line = line.replace("sketch = ", f"{sketch_name} = ")
        
        if plane_def_line:
            script_lines.append(plane_def_line)
        if workplane_def_line:
            script_lines.append(workplane_def_line)
    
    # Process sketch actions
    for action in sketch_actions:
        action_lines = action.split('\n')
        for line in action_lines:
            line = line.strip()
            if not line or line.startswith("plane = ") or line.startswith("sketch = cq.Workplane("):
                continue
            
            if line.startswith("sketch."):
                operation = line.replace("sketch.", "")
                script_lines.append(f"{sketch_name} = {sketch_name}.{operation}")
            elif line.startswith("sketch = sketch."):
                operation = line.replace("sketch = sketch.", "")
                script_lines.append(f"{sketch_name} = {sketch_name}.{operation}")
    
    # Add revolve operation
    axis_start_str = f"({round(axis_start[0], 3)+1e-3}, {round(axis_start[1], 3)+1e-3}, {round(axis_start[2], 3)+1e-3})"
    axis_end_str = f"({round(axis_end[0], 3)+1e-3}, {round(axis_end[1], 3)+1e-3}, {round(axis_end[2], 3)+1e-3})"
    
    script_lines.append(f"result = {sketch_name}.revolve(angleDegrees={round(angle_degrees, 3)}, axisStart={axis_start_str}, axisEnd={axis_end_str})")
    script_lines.append(f"cq.exporters.export(result, '{output_stl_path}')")


    script_lines.append(f"print('Successfully revolved and exported to {output_stl_path}')")
    
    return "\n".join(script_lines)


def test_revolve_operation_multi_axis(axis_to_insts, symmetric_axes, gt_mesh, output_folder, sketch_idx, origin, normal, xdir, alpha=0.01, normalize=True, points=None, inside_a=None):
    """
    Test revolve operation at different angles (90°, 180°, 270°, 360°) for ALL symmetric axes and return best IoU.
    Each axis uses its own cut loops.
    
    Args:
        axis_to_insts: Dict mapping axis angle to cut sketch action instances
        symmetric_axes: List of dicts with 'angle', 'axis_3d_start', 'axis_3d_end' for each symmetric axis
        gt_mesh: Ground truth mesh
        output_folder: Output folder
        sketch_idx: Sketch index
        origin: 3D origin of the plane
        normal: 3D normal vector of the plane
        xdir: 3D x-direction of the plane
        alpha: Alpha for IoU computation
        normalize: Whether to normalize meshes before IoU computation
        points: Precomputed sample points
        inside_a: Precomputed inside ground truth mask
        
    Returns:
        (best_iou, best_angle, best_axis_angle) or (0.0, None, None) if all fail
    """
    test_angles = [360]
    results = []
    
    print(f"  Testing revolve operation for sketch {sketch_idx} with {len(symmetric_axes)} symmetric axes at angles {test_angles}")
    
    # Ensure best_extrusions folder exists
    os.makedirs(f'{output_folder}/best_extrusions', exist_ok=True)
    
    for sym_axis in symmetric_axes:
        axis_angle_deg = sym_axis['angle']
        axis_start = sym_axis['axis_3d_start']
        axis_end = sym_axis['axis_3d_end']
        
        # Get the cut instructions for this specific axis
        insts = axis_to_insts.get(axis_angle_deg)
        if insts is None:
            print(f"    Axis {axis_angle_deg}°: No cut loops available, skipping")
            continue
        
        for angle in test_angles:
            try:
                worker_id = os.getpid()
                timestamp = int(time.time() * 1000000)
                unique_suffix = f"worker_{worker_id}_{timestamp}"
                
                # Use temporary files for revolve operations
                temp_stl_path = f'{output_folder}/temp_revolve_{unique_suffix}.stl'
                temp_script_path = f'{output_folder}/temp_revolve_{unique_suffix}.py'
                
                # Generate script with plane information
                script_content = generate_cadquery_revolve_script(insts, axis_start, axis_end, angle, temp_stl_path,
                                                                 origin=origin, normal=normal, xdir=xdir)
                
                success = execute_cadquery_script(script_content, temp_stl_path, temp_script_path)
                
                if success:
                    # Save GT mesh to a stable path so the IoU cache stays warm
                    # across the inner-loop calls.
                    gt_cache = os.path.join(output_folder, '_revolve_gt_cached.stl')
                    if not os.path.exists(gt_cache):
                        gt_mesh.export(gt_cache)
                    iou = compute_iou(gt_cache, temp_stl_path)
                    
                    results.append((iou, angle, axis_angle_deg))
                    print(f"    Axis {axis_angle_deg}° Revolve {angle}°: IoU = {iou:.6f}")
                    
                    # Clean up temporary files
                    try:
                        os.unlink(temp_stl_path)
                        os.unlink(temp_script_path)
                    except:
                        pass
                else:
                    print(f"    Axis {axis_angle_deg}° Revolve {angle}°: Failed to execute")
                    # Clean up on failure too
                    try:
                        os.unlink(temp_stl_path)
                        os.unlink(temp_script_path)
                    except:
                        pass
                    
            except Exception as e:
                print(f"    Axis {axis_angle_deg}° Revolve {angle}°: Error - {e}")
    
    if results:
        best_iou, best_angle, best_axis_angle = max(results, key=lambda x: x[0])
        return best_iou, best_angle, best_axis_angle
    
    return 0.0, None, None


class TimeoutError(Exception):
    """Custom timeout exception"""
    pass


def timeout_handler(signum, frame):
    """Signal handler for timeout"""
    raise TimeoutError("Operation timed out")


def generate_generic_script(code: str, output_stl_path: str, n: int = 1) -> str:
    """Script for a self-contained ('generic') op, e.g. a loft or sweep from
    analyze_sweep_loft.py, whose code defines `solid_gen_{N}`."""
    body = code.replace('{N}', str(n))
    return (f"import cadquery as cq\nimport math\n\n{body}\n\nresult = solid_gen_{n}\n"
            f"cq.exporters.export(result, '{output_stl_path}')\n")


def execute_cadquery_script(script_content: str, output_stl_path: str, save_script_path: str = None) -> bool:
    """
    Execute a CadQuery script and export STL file.
    
    Args:
        script_content: Python script content with CadQuery operations
        output_stl_path: Path where to save the resulting STL file
        save_script_path: Optional path to save the script file permanently
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Determine script path
        if save_script_path:
            script_path = save_script_path
            # Ensure directory exists
            os.makedirs(os.path.dirname(script_path), exist_ok=True)
        else:
            # Create temporary Python script
            tmp_script = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
            script_path = tmp_script.name
            tmp_script.close()
        
        # Write script content
        with open(script_path, 'w') as f:
            f.write(script_content)
        
        print(f"Executing CadQuery script: {script_path}")
        print(f"Expected output: {output_stl_path}")
        
        # Execute the script in the parent's Python interpreter.
        import sys as _sys
        _t0 = time.time()
        import cq_worker
        if cq_worker.enabled():
            # Same script, same STL; run in a long-lived interpreter that has
            # already imported cadquery (see cq_worker.py).
            ok, err = cq_worker.run_script(script_content, script_path, timeout=60)
            log_event("cq_exec", duration=time.time() - _t0, ok=ok, worker=True)
            if not save_script_path:
                try:
                    os.unlink(script_path)
                except OSError:
                    pass
            if ok and os.path.exists(output_stl_path):
                print(f"✓ Successfully generated STL: {output_stl_path}")
                return True
            print(f"✗ CadQuery script execution failed: {err if not ok else 'STL not found'}")
            return False
        # Own session so a timeout can kill the whole process group (a child
        # holding the stdout pipe would otherwise block `communicate`).
        proc = subprocess.Popen([_sys.executable, script_path], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            out, err = proc.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()
            proc.communicate()
            raise
        result = subprocess.CompletedProcess(proc.args, proc.returncode, out, err)
        log_event("cq_exec", duration=time.time() - _t0, ok=result.returncode == 0)
        
        # Clean up temporary script if it was temporary
        if not save_script_path:
            try:
                os.unlink(script_path)
            except:
                pass
        
        if result.returncode == 0:
            if os.path.exists(output_stl_path):
                print(f"✓ Successfully generated STL: {output_stl_path}")
                return True
            else:
                print(f"✗ Script executed but STL not found: {output_stl_path}")
                print(f"Script stdout: {result.stdout}")
                print(f"Script stderr: {result.stderr}")
                return False
        else:
            print(f"✗ CadQuery script execution failed:")
            print(f"Return code: {result.returncode}")
            print(f"Stdout: {result.stdout}")
            print(f"Stderr: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"✗ CadQuery script execution timed out after 60 seconds")
        return False
    except (TimeoutError, _builtins.TimeoutError):
        # The caller's SIGALRM watchdog (this module shadows the builtin name);
        # let it abandon the task.
        raise
    except Exception as e:
        print(f"✗ Error executing CadQuery script: {e}")
        return False


def compute_iou(gt_path: str, gen_path: str, normalize: bool = True) -> float:
    """CPU mesh-boolean IoU: vol(A ∩ B) / vol(A ∪ B) via trimesh + manifold3d.

    Returns 0.0 if either file is missing/empty or the boolean op fails.
    `normalize` rescales the ground-truth mesh to a [-1, 1] cube first.
    """
    try:
        if not os.path.exists(gt_path) or not os.path.exists(gen_path):
            print(f"Missing files: gt={os.path.exists(gt_path)}, gen={os.path.exists(gen_path)}")
            return 0.0
        if os.path.getsize(gt_path) == 0 or os.path.getsize(gen_path) == 0:
            print(f"Empty files: gt={os.path.getsize(gt_path)}, gen={os.path.getsize(gen_path)}")
            return 0.0
        _t0 = time.time()
        _iou = mesh_iou_cpu_boolean(gt_path, gen_path, normalize=normalize)
        log_event("iou", duration=time.time() - _t0)
        return _iou
    except (TimeoutError, _builtins.TimeoutError):
        raise
    except Exception as e:
        print(f"IoU computation failed: {e}")
        return 0.0


def generate_cadquery_script_multi_height(sketch_actions_list: List[List[str]], heights: List[float], output_stl_path: str) -> str:
    """
    Generate a complete CadQuery script from sketch actions and extrusion heights.
    
    Args:
        sketch_actions_list: List of sketch action lists (each sketch is a list of strings)
        heights: List of extrusion heights (one per sketch)
        output_stl_path: Path where to save the STL file
        
    Returns:
        Complete Python script content
    """
    script_lines = ["import cadquery as cq", "import math", ""]
    
    solid_names = []
    
    for i, (sketch_actions, height) in enumerate(zip(sketch_actions_list, heights)):
        if not sketch_actions:
            continue
            
        # Add index suffix to plane and sketch names
        plane_name = f"plane_{i+1}"
        sketch_name = f"sketch_{i+1}"
        solid_name = f"solid_{i+1}"
        
        # Find plane definition and close statements to identify loops
        plane_def_line = None
        workplane_def_line = None
        close_indices = []
        
        for idx, action in enumerate(sketch_actions):
            action_lines = action.split('\n')
            for line in action_lines:
                line = line.strip()
                if line.startswith("plane = "):
                    plane_def_line = line.replace("plane = ", f"{plane_name} = ")
                elif line.startswith("sketch = cq.Workplane("):
                    if "cq.Workplane(plane)" in line:
                        workplane_def_line = f"{sketch_name} = cq.Workplane({plane_name})"
                    else:
                        workplane_def_line = line.replace("sketch = ", f"{sketch_name} = ")
                elif "close" in line or "circle" in line:
                    close_indices.append(idx)
        
        # Add plane and sketch definitions
        if plane_def_line:
            script_lines.append(plane_def_line)
        if workplane_def_line:
            script_lines.append(workplane_def_line)
        
        # Process loops
        loop_names = []
        current_loop_idx = 0
        current_action_idx = 0
        
        while current_action_idx < len(sketch_actions):
            # Find next close statement
            next_close_idx = None
            for close_idx in close_indices:
                if close_idx >= current_action_idx:
                    next_close_idx = close_idx
                    break
            
            if next_close_idx is None:
                break
                
            # Process actions until close
            loop_name = f"loop_{current_loop_idx + 1}"
            loop_names.append(loop_name)
            first_action_in_loop = True
            
            for action_idx in range(current_action_idx, next_close_idx + 1):
                if action_idx >= len(sketch_actions):
                    break
                    
                action = sketch_actions[action_idx]
                action_lines = action.split('\n')
                
                for line in action_lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Skip plane and workplane definitions (already handled)
                    if line.startswith("plane = ") or line.startswith("sketch = cq.Workplane("):
                        continue
                    
                    if line.startswith("sketch.moveTo("):
                        # First action in loop - create loop variable
                        coords = line.replace("sketch.moveTo(", "").replace(")", "")
                        modified_line = f"{loop_name} = {sketch_name}.moveTo({coords})"
                        script_lines.append(modified_line)
                        first_action_in_loop = False
                    elif line.startswith("sketch."):
                        # Chain loop operations
                        operation = line.replace("sketch.", "")
                        modified_line = f"{loop_name} = {loop_name}.{operation}"
                        script_lines.append(modified_line)
                    elif line.startswith("sketch = sketch."):
                        # Chained operations like "sketch = sketch.threePointArc(...)"
                        operation = line.replace("sketch = sketch.", "")
                        modified_line = f"{loop_name} = {loop_name}.{operation}"
                        script_lines.append(modified_line)
                    elif "close" in line:
                        # Close the loop
                        script_lines.append(f"{loop_name} = {loop_name}.close()")
                        
            current_loop_idx += 1
            current_action_idx = next_close_idx + 1
        
        # Add all loops to sketch
        if loop_names:
            add_chain = f"{sketch_name}={sketch_name}.add({loop_names[0]})"
            for loop_name in loop_names[1:]:
                add_chain += f".add({loop_name})"
            script_lines.append(add_chain)
        
        # Add extrusion with specific height
        script_lines.append(f"{solid_name} = {sketch_name}.extrude({round(height, 3)})")
        solid_names.append(solid_name)
        script_lines.append("")
    
    # Union all solids if there are multiple
    if len(solid_names) > 1:
        # Start with first solid
        union_script = f"result = {solid_names[0]}"
        script_lines.append(union_script)
        
        # Combine remaining solids via `.add()` — produces a Compound that
        # exports correct geometry without invoking OCC's brittle/expensive
        # boolean union. Downstream uses manifold3d to clean the STL.
        for solid_name in solid_names[1:]:
            script_lines.append(f"result = result.add({solid_name})")

        
        # Export the result
        script_lines.append(f"cq.exporters.export(result, '{output_stl_path}')")
        script_lines.append("print(f'Successfully exported {0} solids to {1}')".format(len(solid_names), output_stl_path))
    elif len(solid_names) == 1:
        # Just one solid, export directly
        script_lines.append(f"result = {solid_names[0]}")
        script_lines.append(f"cq.exporters.export(result, '{output_stl_path}')")
        script_lines.append(f"print('Successfully exported 1 solid to {output_stl_path}')")
    else:
        # No solids, create empty script that just creates an empty file
        script_lines.append(f"# No solids to export")
        script_lines.append(f"print('No solids to export - creating empty file')")
        script_lines.append(f"open('{output_stl_path}', 'w').close()")
    
    return "\n".join(script_lines)


def generate_cadquery_script(sketch_actions_list: List[List[str]], height: float, output_stl_path: str) -> str:
    """
    Generate a complete CadQuery script from sketch actions and single extrusion height.
    
    Args:
        sketch_actions_list: List of sketch action lists (each sketch is a list of strings)
        height: Extrusion height (applied to all sketches)
        output_stl_path: Path where to save the STL file
        
    Returns:
        Complete Python script content
    """
    heights = [height] * len(sketch_actions_list)
    return generate_cadquery_script_multi_height(sketch_actions_list, heights, output_stl_path)


def with_timeout(timeout_seconds):
    """Decorator to enforce timeout on function execution"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Set up signal handler
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(int(timeout_seconds))
            
            try:
                result = func(*args, **kwargs)
                signal.alarm(0)  # Cancel alarm
                return result
            except TimeoutError:
                signal.alarm(0)  # Cancel alarm
                print(f"  TIMEOUT: Function {func.__name__} exceeded {timeout_seconds}s")
                return None
            except Exception as e:
                signal.alarm(0)  # Cancel alarm
                print(f"  ERROR in {func.__name__}: {e}")
                return None
            finally:
                signal.signal(signal.SIGALRM, old_handler)
        return wrapper
    return decorator


def adaptive_height_search(insts, faces_idx, gt_mesh, h_min, h_max, max_iterations=7, sketch_idx=None, height_type="pos", timeout_seconds=100, max_height_eval_time=300, output_folder="search", alpha=0.01, normalize=True, points=None, inside_a=None):
    """
    Adaptive height search exploiting the linear/quadratic nature of IoU curves.
    Uses golden section search with intelligent sampling.
    
    Args:
        timeout_seconds: Maximum time to spend on this search before giving up
        max_height_eval_time: Maximum time to spend on a single height evaluation
        normalize: Whether to normalize meshes before IoU computation
        points: Precomputed sample points
        inside_a: Precomputed inside ground truth mask
    """
    search_start_time = time.time()
    height_iou_pairs = []
    
    @with_timeout(max_height_eval_time)
    def evaluate_height_with_timeout(h):
        """Helper to evaluate a single height with hard timeout"""
        # Check if already evaluated
        for cached_h, cached_iou in height_iou_pairs:
            if abs(cached_h - h) < 1e-6:
                return cached_iou
        
        eval_start_time = time.time()
        
        # Convert insts to sketch actions list format
        sketch_actions_list = [insts]  # Assuming insts is already a list of sketch actions
        
        # Generate and execute CadQuery script with unique worker naming
        worker_id = os.getpid()
        timestamp = int(time.time() * 1000000)  # microsecond timestamp
        unique_suffix = f"worker_{worker_id}_{timestamp}"
        output_path = f'{output_folder}/adaptive_{sketch_idx}_{height_type}_{unique_suffix}'
        
        script_content = generate_cadquery_script(sketch_actions_list, h, f'{output_path}.stl')
        script_path = f'{output_path}_h{h}.py'
        success = execute_cadquery_script(script_content, f'{output_path}.stl', script_path)
        
        print(f"  Worker {worker_id}: Height {h}: Script saved to {script_path}, Success={success}")
        
        if not success:
            return 0.0
            
        mesh = trimesh.load(f'{output_path}.stl', force='mesh')
        if mesh is None:
            iou = 0.0
        else:
            try:
                iou_start = time.time()
                # Save GT to a stable path so the IoU cache stays warm.
                gt_path = os.path.join(output_folder, '_height_gt_cached.stl')
                if not os.path.exists(gt_path):
                    gt_mesh.copy().export(gt_path)
                iou = compute_iou(gt_path, f'{output_path}.stl')
                
                iou_duration = time.time() - iou_start
                print(f"IoU computed for height {h}: {iou:.6f} (IoU took {iou_duration:.2f}s)")
            except Exception as e:
                iou = 0.0
                print(f"IoU computation failed for height {h}: {e}")
        
        # Clean up generated files to save space
        try:
            if os.path.exists(f'{output_path}.stl'):
                os.unlink(f'{output_path}.stl')
            if os.path.exists(script_path):
                os.unlink(script_path)
        except:
            pass  # Ignore cleanup errors
        
        eval_duration = time.time() - eval_start_time
        print(f"  Height {h} evaluation completed in {eval_duration:.2f}s")
        return iou
    
    def evaluate_height(h):
        """Wrapper for evaluate_height_with_timeout with fallback handling"""
        # Check timeout before starting evaluation
        if time.time() - search_start_time > timeout_seconds:
            print(f"  Timeout reached ({timeout_seconds}s), stopping height search")
            return 0.0
            
        # Check if already evaluated
        for cached_h, cached_iou in height_iou_pairs:
            if abs(cached_h - h) < 1e-6:
                return cached_iou
        
        try:
            result = evaluate_height_with_timeout(h)
            if result is None:  # Timeout occurred
                height_iou_pairs.append((h, 0.0))
                return 0.0
            else:
                height_iou_pairs.append((h, result))
                return result
        except Exception as e:
            print(f"Exception during height {h} evaluation: {e}")
            height_iou_pairs.append((h, 0.0))
            return 0.0
    
    # Initial 5-point sampling with fallback strategy
    initial_ious = [0 for _ in range(5)]
    checks = 0

    while all(iou == 0.0 for iou in initial_ious) and checks < 4:
        # Progressively smaller heights on retry to avoid issues
        scale_factor = 5**checks if checks > 0 else 1
        initial_heights = [(h_min + j * (h_max - h_min) / 4)/scale_factor for j in range(5)]
        initial_ious = [0 for _ in range(len(initial_heights))]
        checks += 1 

        print(f"  Check {checks}: Trying heights {initial_heights}")
        for i, h in enumerate(initial_heights):
            if time.time() - search_start_time > timeout_seconds:
                print(f"  Timeout reached during initial sampling, stopping")
                break
            initial_ious[i] = evaluate_height(h)

    if not initial_ious or all(iou == 0.0 for iou in initial_ious):
        print(f"  No valid IoU values found or timeout reached, returning empty results")
        return [], []
    
    print(f"Initial sampling: {list(zip(initial_heights[:len(initial_ious)], initial_ious))}")
    
    # Find the best initial point
    best_idx = np.argmax(initial_ious)
    
    # Adaptive refinement iterations
    for iteration in range(max_iterations):
        # Check timeout before each iteration
        #     break
            
        # Sort points by height
        sorted_pairs = sorted(height_iou_pairs, key=lambda x: x[0])
        heights_sorted = [pair[0] for pair in sorted_pairs]
        ious_sorted = [pair[1] for pair in sorted_pairs]
        
        if len(heights_sorted) < 3:
            break
            
        # Find current best
        current_best_idx = np.argmax(ious_sorted)
        current_best_h = heights_sorted[current_best_idx]
        current_best_iou = ious_sorted[current_best_idx]
        
        # Determine search intervals around the best point
        search_intervals = []
        
        # Left interval
        if current_best_idx > 0:
            left_h = heights_sorted[current_best_idx - 1]
            if current_best_h - left_h > 1e-6:
                search_intervals.append((left_h, current_best_h))
        
        # Right interval  
        if current_best_idx < len(heights_sorted) - 1:
            right_h = heights_sorted[current_best_idx + 1]
            if right_h - current_best_h > 1e-6:
                search_intervals.append((current_best_h, right_h))
        
        # If no intervals or current best is at boundary, expand search
        if not search_intervals:
            # Expand around current best
            expansion = (h_max - h_min) * 0.1  # 10% of range
            left_bound = max(h_min, current_best_h - expansion)
            right_bound = min(h_max, current_best_h + expansion)
            
            if left_bound < current_best_h:
                search_intervals.append((left_bound, current_best_h))
            if current_best_h < right_bound:
                search_intervals.append((current_best_h, right_bound))
        
        if not search_intervals:
            print(f"Converged after {iteration + 1} iterations")
            break
        
        # Sample new points using golden ratio for each interval
        phi = (1 + np.sqrt(5)) / 2  # Golden ratio
        new_heights = []
        
        for left, right in search_intervals:
            interval_size = right - left
            if interval_size > 1e-6:
                # Golden section points
                h1 = right - interval_size / phi
                h2 = left + interval_size / phi
                
                # Avoid duplicates
                if not any(abs(h1 - cached_h) < 1e-6 for cached_h, _ in height_iou_pairs):
                    new_heights.append(h1)
                if not any(abs(h2 - cached_h) < 1e-6 for cached_h, _ in height_iou_pairs):
                    new_heights.append(h2)
        
        if not new_heights:
            print(f"No new heights to sample, converged after {iteration + 1} iterations")
            break
            
        # Evaluate new heights
        print(f"Iteration {iteration + 1}: Sampling heights {new_heights}")
        for h in new_heights:
            if time.time() - search_start_time > timeout_seconds:
                print(f"  Timeout reached during iteration {iteration + 1}, stopping")
                break
            evaluate_height(h)
    
    # Save plot and data - always plot when we have data
    if height_iou_pairs:
        try:
            heights_plot = [pair[0] for pair in height_iou_pairs]
            ious_plot = [pair[1] for pair in height_iou_pairs]
            
            # Sort for plotting
            sorted_data = sorted(zip(heights_plot, ious_plot))
            heights_plot = [h for h, _ in sorted_data]
            ious_plot = [iou for _, iou in sorted_data]
            
            plt.figure(figsize=(10, 6))
            plt.plot(heights_plot, ious_plot, 'b-o', linewidth=2, markersize=6)
            plt.xlabel('Height')
            plt.ylabel('IoU')
            
            # Use sketch_idx if available, otherwise use a default identifier
            sketch_label = sketch_idx if sketch_idx is not None else "unknown"
            plt.title(f'Adaptive IoU vs Height - Sketch {sketch_label} ({height_type})')
            plt.grid(True, alpha=0.3)
            
            # Highlight best height
            best_idx = np.argmax(ious_plot)
            if ious_plot[best_idx] > 0:
                plt.plot(heights_plot[best_idx], ious_plot[best_idx], 'ro', markersize=10, 
                        label=f'Best: h={heights_plot[best_idx]:.3f}, IoU={ious_plot[best_idx]:.6f}')
                plt.legend()
            
            plt.tight_layout()
            os.makedirs(f'{output_folder}/best_extrusions', exist_ok=True)
            
            # Use sketch_idx if available, otherwise use timestamp for unique naming
            if sketch_idx is not None:
                plot_filename = f'sketch_{sketch_idx}_{height_type}_adaptive_iou_vs_height.png'
                data_filename = f'sketch_{sketch_idx}_{height_type}_adaptive_iou_data.json'
            else:
                timestamp = int(time.time() * 1000)
                plot_filename = f'sketch_unknown_{timestamp}_{height_type}_adaptive_iou_vs_height.png'
                data_filename = f'sketch_unknown_{timestamp}_{height_type}_adaptive_iou_data.json'
            
            plt.savefig(f'{output_folder}/best_extrusions/{plot_filename}', 
                       dpi=150, bbox_inches='tight')
            plt.close()
            print(f"Saved adaptive IoU vs height plot: {plot_filename}")
            
            # Save data
            with open(f'{output_folder}/best_extrusions/{data_filename}', 'w') as f:
                json.dump({
                    'heights': heights_plot,
                    'ious': ious_plot,
                    'best_height': heights_plot[best_idx] if ious_plot[best_idx] > 0 else None,
                    'best_iou': ious_plot[best_idx] if ious_plot[best_idx] > 0 else 0.0,
                    'total_evaluations': len(height_iou_pairs)
                }, f, indent=2)
        except Exception as e:
            print(f"Failed to save adaptive IoU plot for sketch {sketch_idx} ({height_type}): {e}")
    
    # Return IoU values for all evaluated heights in original order
    all_heights = [pair[0] for pair in height_iou_pairs]
    all_ious = [pair[1] for pair in height_iou_pairs]
    
    return all_ious, all_heights


def process_single_sketch_adaptive(args: Tuple[int, List[str], str, float, float, str, float, Any, bool, Any, Any, Any, bool]) -> Dict[str, Any]:
    """
    Worker function to process a single sketch using adaptive height search.
    Also checks for symmetry and tests revolve operations.
    
    Args:
        args: Tuple containing (sketch_idx, insts, gt_stl_path, hmin, hmax, output_folder, alpha, entry, normalize, points, inside_a, revolve_entry, merge_pos_neg)
        revolve_entry: Optional unsplit sketch entry for revolve detection (None to use regular entry)
        merge_pos_neg: If True, merge pos and neg heights into single extrusion with translated origin
        
    Returns:
        Dictionary with sketch processing results
    """
    sketch_idx, insts, gt_stl_path, hmin, hmax, output_folder, alpha, entry, normalize, points, inside_a, revolve_entry, merge_pos_neg = args
    
    try:
        print(f"Worker processing sketch {sketch_idx + 1} with adaptive search")
        
        # Load ground truth mesh in worker
        gt_mesh = trimesh.load(gt_stl_path, force='mesh')
        
        # Check for symmetry using revolve_entry (unsplit loops) if available
        # Otherwise fall back to regular entry (may have split loops)
        symmetry_entry = revolve_entry if revolve_entry is not None else entry
        if revolve_entry is not None:
            print(f"Worker processing sketch {sketch_idx + 1}: Using unsplit revolve entry for symmetry detection")
        
        symmetric_axes = find_symmetry_axis(symmetry_entry, sketch_idx=sketch_idx, output_folder=output_folder)
        
        revolve_iou = 0.0
        revolve_angle = None
        revolve_axis_angle = None
        axis_start = None
        axis_end = None
        
        if symmetric_axes:
            num_axes = len(symmetric_axes)
            axes_str = ', '.join([f"{ax['angle']}°" for ax in symmetric_axes])
            print(f"  Sketch {sketch_idx} detected {num_axes} symmetric axes: [{axes_str}]")
            
            # Get plane information for revolve script generation from symmetry_entry
            # This ensures we use the unsplit loops if revolve_entry was provided
            origin = symmetry_entry.get('origin', [0, 0, 0])
            normal = symmetry_entry.get('normal', [0, 0, 1])
            xdir = symmetry_entry.get('xdir', [1, 0, 0])
            
            # Get 3D loops and project to 2D (same as in plot_symmetry_axes.py)
            # Use symmetry_entry to get unsplit loops for better revolve profiles
            loops_3d = symmetry_entry.get('loops_3d', symmetry_entry.get('loops', []))
            loops_2d = []
            for loop_3d in loops_3d:
                loop_2d = project_3d_to_2d(loop_3d, origin, normal, xdir)
                loops_2d.append(loop_2d.tolist())
            
            # Prepare cut loops and modified instances for EACH symmetric axis
            axis_to_insts = {}
            
            for sym_axis in symmetric_axes:
                sym_axis_angle = sym_axis['angle']
                
                # Cut loops at symmetry axis (in 2D)
                cut_loops_2d = []
                for loop_2d in loops_2d:
                    cut_loop = cut_loop_at_symmetry_axis(loop_2d, sym_axis_angle)
                    if len(cut_loop) >= 3:
                        cut_loops_2d.append(cut_loop)
                
                if cut_loops_2d:
                    # Create modified entry with cut loops
                    # Use symmetry_entry as base to preserve plane info and unsplit loop structure
                    modified_entry = symmetry_entry.copy()
                    modified_entry['loops'] = cut_loops_2d
                    
                    # Rebuild sketch actions with cut loops for this specific axis
                    modified_insts = build_action_instances_from_entry(modified_entry)
                    axis_to_insts[sym_axis_angle] = modified_insts
                else:
                    print(f"  Warning: No valid cut loops for axis {sym_axis_angle}°, skipping this axis")
            
            # Test revolve operation with ALL symmetric axes (each with its own cut loops)
            if axis_to_insts:
                revolve_iou, revolve_angle, revolve_axis_angle = test_revolve_operation_multi_axis(
                    axis_to_insts, symmetric_axes, gt_mesh, 
                    output_folder, sketch_idx, origin, normal, xdir, alpha
                )
                
                # Save axis endpoints for best result
                if revolve_axis_angle is not None:
                    best_axis = next((ax for ax in symmetric_axes if ax['angle'] == revolve_axis_angle), symmetric_axes[0])
                    axis_start = best_axis['axis_3d_start']
                    axis_end = best_axis['axis_3d_end']
                    print(f"  Best revolve: Axis {revolve_axis_angle}° at {revolve_angle}° with IoU {revolve_iou:.6f}")
            else:
                print(f"  Warning: No valid cut loops for any symmetric axis, skipping revolve operations")
        
        # Process positive heights using adaptive search
        if hmax > 1e-6:
            pos_iou, pos_heights = adaptive_height_search(
                insts, None, gt_mesh, max(1e-6, hmin), hmax, 
                max_iterations=5, sketch_idx=sketch_idx, height_type="pos", 
                timeout_seconds=1800, output_folder=output_folder, alpha=alpha
            )
        else:
            pos_iou, pos_heights = [], []
        
        # Process negative heights using adaptive search
        if hmin < -1e-6:
            neg_iou, neg_heights = adaptive_height_search(
                insts, None, gt_mesh, hmin, -max(1e-6, hmin),
                max_iterations=5, sketch_idx=sketch_idx, height_type="neg", 
                timeout_seconds=1800, output_folder=output_folder, alpha=alpha
            )
        else:
            neg_iou, neg_heights = [], []
        
        # Find best heights with tie-breaking by smallest absolute height
        def select_best_height_with_tiebreaker(iou_list, height_list, tolerance=0.0001):
            if not iou_list or len(height_list) == 0 or not any(iou_list):
                return None
            
            max_iou = max(iou_list)
            # Find all indices within tolerance of max IoU
            candidate_indices = [i for i, iou in enumerate(iou_list) if abs(iou - max_iou) <= tolerance]
            
            # Among candidates, select the one with smallest absolute height
            best_idx = min(candidate_indices, key=lambda i: abs(height_list[i]))
            
            # Check if final height is below threshold - if so, neglect it
            if abs(height_list[best_idx]) < 0.0001:
                print(f"Best height {height_list[best_idx]:.6f} is below 0.0001 threshold, neglecting")
                return None
            
            return best_idx
        
        best_pos_idx = select_best_height_with_tiebreaker(pos_iou, pos_heights)
        best_neg_idx = select_best_height_with_tiebreaker(neg_iou, neg_heights)
        
        pos_h = pos_heights[best_pos_idx] if best_pos_idx is not None else None
        neg_h = neg_heights[best_neg_idx] if best_neg_idx is not None else None
        pos_iou_val = pos_iou[best_pos_idx] if best_pos_idx is not None else 0.0
        neg_iou_val = neg_iou[best_neg_idx] if best_neg_idx is not None else 0.0
        
        # Merge positive and negative extrusions if both exist and merge is enabled
        merged_insts = None
        merged_h = None
        merged_iou = 0.0
        if merge_pos_neg and pos_h is not None and neg_h is not None and abs(neg_h) > 1e-6:
            print(f"  Sketch {sketch_idx}: Merging pos_h={pos_h:.4f} and neg_h={neg_h:.4f}")
            
            # New height is pos_h - neg_h (since neg_h is negative, this adds them)
            merged_h = pos_h - neg_h
            
            # Translate origin by neg_h * normal
            origin = np.array(entry.get('origin', [0, 0, 0]))
            normal = np.array(entry.get('normal', [0, 0, 1]))
            normal = normal / np.linalg.norm(normal)  # Normalize
            
            translated_origin = origin + neg_h * normal
            
            # Create modified entry with translated origin
            merged_entry = entry.copy()
            merged_entry['origin'] = translated_origin.tolist()
            
            # Rebuild instructions with translated origin
            merged_insts = build_action_instances_from_entry(merged_entry)
            
            # Test merged extrusion to get IoU
            try:
                sketch_actions_list = [merged_insts]
                worker_id = os.getpid()
                timestamp = int(time.time() * 1000000)
                unique_suffix = f"worker_{worker_id}_{timestamp}"
                test_path = f'{output_folder}/test_merged_{sketch_idx}_{unique_suffix}'
                
                script_content = generate_cadquery_script(sketch_actions_list, merged_h, f'{test_path}.stl')
                success = execute_cadquery_script(script_content, f'{test_path}.stl', f'{test_path}.py')
                
                if success and os.path.exists(f'{test_path}.stl'):
                    merged_iou = compute_iou(gt_stl_path, f'{test_path}.stl')
                    print(f"  Merged extrusion: h={merged_h:.4f}, IoU={merged_iou:.6f} (vs pos={pos_iou_val:.6f}, neg={neg_iou_val:.6f})")
                    
                    # Clean up test file
                    try:
                        os.unlink(f'{test_path}.stl')
                        os.unlink(f'{test_path}.py')
                    except:
                        pass
                else:
                    print(f"  Merged extrusion failed to generate")
                    merged_h = None
                    merged_insts = None
                    
            except Exception as e:
                print(f"  Error testing merged extrusion: {e}")
                merged_h = None
                merged_insts = None
        
        # Determine best operation (extrude vs revolve) - for logging purposes
        # But we'll keep all IoU values so greedy search can choose
        use_revolve = revolve_iou > max(pos_iou_val, neg_iou_val)
        
        if use_revolve:
            print(f"  Sketch {sketch_idx}: Best is REVOLVE ({revolve_angle}°, IoU={revolve_iou:.6f})")
        else:
            print(f"  Sketch {sketch_idx}: Best is EXTRUDE (IoU={max(pos_iou_val, neg_iou_val):.6f})")
        
        # Save best positive extrusion mesh
        if pos_h is not None:
            try:
                sketch_actions_list = [insts]
                success = export_stl_cadquery(sketch_actions_list, pos_h, 
                                            f'{output_folder}/best_extrusions/sketch_{sketch_idx}_pos', save_script=True)
                if not success:
                    print(f"Failed to save best positive extrusion for sketch {sketch_idx}")
            except Exception as e:
                print(f"Failed to save best positive extrusion for sketch {sketch_idx}: {e}")

        # Save best negative extrusion mesh
        if neg_h is not None:
            try:
                sketch_actions_list = [insts]
                success = export_stl_cadquery(sketch_actions_list, neg_h, 
                                            f'{output_folder}/best_extrusions/sketch_{sketch_idx}_neg', save_script=True)
                if not success:
                    print(f"Failed to save best negative extrusion for sketch {sketch_idx}")
            except Exception as e:
                print(f"Failed to save best negative extrusion for sketch {sketch_idx}: {e}")
        
        # Save best revolve mesh if applicable (already saved during test_revolve_operation)
        # The files are saved with names like: sketch_X_axis000_revolve_90deg.stl
        if use_revolve and revolve_angle is not None and revolve_axis_angle is not None:
            print(f"  Best revolve mesh already saved: sketch_{sketch_idx}_axis{revolve_axis_angle:03d}_revolve_{revolve_angle}deg.stl")
            # Note: The mesh was already saved during test_revolve_operation with proper plane info
        
        zero_only = (pos_iou_val == 0.0 and neg_iou_val == 0.0 and revolve_iou == 0.0 and merged_iou == 0.0)
        
        return {
            'sketch_idx': sketch_idx,
            'insts': insts,
            'faces_idx': None,
            'pos_h': pos_h,
            'pos_iou': pos_iou_val,
            'neg_h': neg_h,
            'neg_iou': neg_iou_val,
            'merged_h': merged_h,
            'merged_iou': merged_iou,
            'merged_insts': merged_insts,
            'revolve_angle': revolve_angle,
            'revolve_iou': revolve_iou,
            'revolve_axis_start': axis_start,
            'revolve_axis_end': axis_end,
            'revolve_axis_angle': revolve_axis_angle,
            'is_symmetric': len(symmetric_axes) > 0,
            'use_revolve': use_revolve,
            'zero_only': zero_only,
            'success': True,
            'error': None
        }
        
    except Exception as e:
        print(f"Error processing sketch {sketch_idx}: {e}")
        import traceback
        traceback.print_exc()
        return {
            'sketch_idx': sketch_idx,
            'insts': insts,
            'faces_idx': None,
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
            'zero_only': True,
            'success': False,
            'error': str(e)
        }
    """
    Worker function to evaluate a single height for a sketch.
    
    Args:
        args: Tuple containing (sketch_idx, insts, faces_idx, gt_stl_path, height, h_min, h_max, output_folder, alpha)
        
    Returns:
        Dictionary with evaluation results
    """
    sketch_idx, insts, faces_idx, gt_stl_path, height, h_min, h_max, output_folder, alpha = args
    
    try:
        # Create unique filename for this worker to avoid conflicts
        worker_id = os.getpid()
        timestamp = int(time.time() * 1000000)  # microsecond timestamp
        unique_suffix = f"worker_{worker_id}_{timestamp}"
        
        print(f"  Worker {worker_id}: Processing sketch {sketch_idx}, height {height:.6f}")
        
        # Convert insts to sketch actions list format
        sketch_actions_list = [insts]
        
        # Generate and execute CadQuery script with unique naming
        output_path = f'{output_folder}/sketch_{sketch_idx}_h_{height:.6f}_{unique_suffix}'
        script_content = generate_cadquery_script(sketch_actions_list, height, f'{output_path}.stl')
        script_path = f'{output_path}.py'
        
        success = execute_cadquery_script(script_content, f'{output_path}.stl', script_path)
        
        if not success:
            print(f"  Worker {worker_id}: Script execution failed for height {height:.6f}")
            return {
                'sketch_idx': sketch_idx,
                'height': height,
                'iou': 0.0,
                'success': False,
                'error': 'Script execution failed'
            }
        
        # Check if STL file was created and has content
        if not os.path.exists(f'{output_path}.stl') or os.path.getsize(f'{output_path}.stl') == 0:
            print(f"  Worker {worker_id}: STL file not created or empty for height {height:.6f}")
            return {
                'sketch_idx': sketch_idx,
                'height': height,
                'iou': 0.0,
                'success': False,
                'error': 'STL file not created or empty'
            }
        
        # Compute IoU using thread-safe GPU function
        iou = compute_iou(gt_stl_path, f'{output_path}.stl')
        
        print(f"  Worker {worker_id}: Height {height:.6f} -> IoU {iou:.6f}")
        
        # Clean up generated files to save space
        try:
            if os.path.exists(f'{output_path}.stl'):
                os.unlink(f'{output_path}.stl')
            if os.path.exists(script_path):
                os.unlink(script_path)
        except:
            pass  # Ignore cleanup errors
        
        return {
            'sketch_idx': sketch_idx,
            'height': height,
            'iou': iou,
            'success': True,
            'error': None
        }
        
    except Exception as e:
        print(f"  Worker {worker_id}: Exception for height {height:.6f}: {e}")
        return {
            'sketch_idx': sketch_idx,
            'height': height,
            'iou': 0.0,
            'success': False,
            'error': str(e)
        }



def precompute_sketch_heights_parallel(data, gt_mesh, hmin: float, hmax: float, num_workers: int = 4, 
                                     output_folder: str = "search", alpha: float = 0.01, normalize: bool = True, points=None, inside_a=None, revolve_data=None, merge_pos_neg: bool = False):
    """
    Parallel version using adaptive height search for each sketch.
    Also checks for symmetry and tests revolve operations.
    
    Args:
        data: List of sketch data entries (may have split loops)
        gt_mesh: Ground truth mesh
        hmin: Minimum height range
        hmax: Maximum height range
        num_workers: Number of worker processes
        output_folder: Output folder for results
        alpha: Alpha parameter for IoU computation
        normalize: Whether to normalize meshes before IoU computation
        points: Precomputed sample points
        inside_a: Precomputed inside ground truth mask
        revolve_data: Optional list of unsplit axis sketch entries for revolve detection
        merge_pos_neg: If True, merge pos and neg heights into single extrusion with translated origin
        
    Returns:
        List of sketch processing results
    """
    import os
    import pickle
    import tempfile
    
    os.makedirs(f'{output_folder}/best_extrusions', exist_ok=True)
    
    # Check if precomputed results exist
    precomp_file = f'{output_folder}/precomputed_sketch_heights_parallel.pkl'
    if os.path.exists(precomp_file):
        print("Loading precomputed parallel sketch heights from disk...")
        with open(precomp_file, 'rb') as f:
            return pickle.load(f)
    
    print(f"Running parallel adaptive extrusion optimization with {num_workers} workers...")
    
    # Save ground truth mesh to temporary file for worker access
    with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as tmp_gt:
        gt_mesh.export(tmp_gt.name)
        gt_stl_path = tmp_gt.name
    
    try:
        # Prepare sketch data
        sketch_data_list = []
        for entry in data:
            insts = build_action_instances_from_entry(entry)
            sketch_data_list.append((insts, entry))
        
        print(f"Processing {len(sketch_data_list)} sketches with adaptive search and symmetry detection...")
        
        # Match sketches with revolve entries if provided
        # Revolve entries contain unsplit axis-aligned sketches for better symmetry detection
        revolve_entry_map = {}
        if revolve_data is not None:
            print(f"Matching {len(sketch_data_list)} sketches with {len(revolve_data)} revolve entries...")
            for sketch_idx, (insts, entry) in enumerate(sketch_data_list):
                # Match by origin and normal (axis-aligned sketches)
                origin = entry.get('origin')
                normal = entry.get('normal')
                if origin and normal:
                    for revolve_entry in revolve_data:
                        r_origin = revolve_entry.get('origin')
                        r_normal = revolve_entry.get('normal')
                        if r_origin and r_normal:
                            # Check if origin and normal match (with small tolerance)
                            import numpy as np
                            if (np.allclose(origin, r_origin, atol=1e-6) and 
                                np.allclose(normal, r_normal, atol=1e-6)):
                                revolve_entry_map[sketch_idx] = revolve_entry
                                print(f"  Matched sketch {sketch_idx} with revolve entry (unsplit loops)")
                                break
            print(f"Matched {len(revolve_entry_map)} sketches with revolve entries")
        
        # Prepare arguments for parallel processing
        worker_args = []
        for sketch_idx, (insts, entry) in enumerate(sketch_data_list):
            revolve_entry = revolve_entry_map.get(sketch_idx, None)
            args = (sketch_idx, insts, gt_stl_path, hmin, hmax, output_folder, alpha, entry, normalize, points, inside_a, revolve_entry, merge_pos_neg)
            worker_args.append(args)
        
        # Process sketches in parallel using adaptive search
        from iou import warm_manifold
        warm_manifold(gt_stl_path, normalize)
        with guarded_pool(num_workers, initializer=warm_manifold, initargs=(gt_stl_path, normalize)) as pool:
            results, _ = safe_pool_map(pool, process_single_sketch_adaptive, worker_args, stall=900)
        results = [r for r in results if r is not None]
        
        # Process results
        final_results = []
        for result in results:
            if result['success']:
                final_results.append({
                    'insts': result['insts'],
                    'faces_idx': result['faces_idx'],
                    'pos_h': result['pos_h'],
                    'pos_iou': result['pos_iou'],
                    'neg_h': result['neg_h'],
                    'neg_iou': result['neg_iou'],
                    'merged_h': result.get('merged_h'),
                    'merged_iou': result.get('merged_iou', 0.0),
                    'merged_insts': result.get('merged_insts'),
                    'revolve_angle': result.get('revolve_angle'),
                    'revolve_iou': result.get('revolve_iou', 0.0),
                    'revolve_axis_start': result.get('revolve_axis_start'),
                    'revolve_axis_end': result.get('revolve_axis_end'),
                    'is_symmetric': result.get('is_symmetric', False),
                    'use_revolve': result.get('use_revolve', False),
                    'zero_only': result['zero_only']
                })
                
                if result.get('use_revolve'):
                    print(f"Sketch {result['sketch_idx']}: REVOLVE {result['revolve_angle']}°, IoU={result['revolve_iou']:.6f}")
                else:
                    print(f"Sketch {result['sketch_idx']}: EXTRUDE pos_h={result['pos_h']}, pos_iou={result['pos_iou']:.6f}, neg_h={result['neg_h']}, neg_iou={result['neg_iou']:.6f}")
            else:
                print(f"Sketch {result['sketch_idx']} failed: {result['error']}")
                # Still add failed sketch with default values
                final_results.append({
                    'insts': result['insts'],
                    'faces_idx': result['faces_idx'],
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
        
        # Save precomputed results
        with open(precomp_file, 'wb') as f:
            pickle.dump(final_results, f)
        print("Saved precomputed parallel sketch heights to disk.")
        
        return final_results
        
    finally:
        # Clean up temporary ground truth file
        try:
            os.unlink(gt_stl_path)
        except:
            pass


def export_stl_cadquery(sketch_actions_list: List[List[str]], height: float, filename: str, save_script: bool = True) -> bool:
    """
    Generate and execute CadQuery script to create STL file.
    
    Args:
        sketch_actions_list: List of sketch action lists
        height: Extrusion height
        filename: Base filename (without .stl extension)
        save_script: Whether to save the script permanently for debugging
        
    Returns:
        True if successful, False otherwise
    """
    output_stl_path = f"{filename}.stl"
    script_content = generate_cadquery_script(sketch_actions_list, height, output_stl_path)
    
    # Save script permanently if requested
    script_path = None
    if save_script:
        script_path = f"{filename}.py"
    
    return execute_cadquery_script(script_content, output_stl_path, script_path)


def _revolve_frame(group):
    """Explicit plane for a revolve group when the identity fix recorded one;
    empty (stock behaviour: plane recovered from the action strings) otherwise."""
    if group.get('revolve_origin') is None:
        return {}
    return {'origin': group['revolve_origin'], 'normal': group['revolve_normal'],
            'xdir': group['revolve_xdir']}


def calculate_extrusion_volume(group):
    """Calculate the volume of a single extrusion or revolve group"""
    try:
        # Create a temporary STL for this single operation
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as tmp_file:
            temp_path = tmp_file.name
        
        script_path = temp_path.replace('.stl', '.py')
        
        if group.get('type') == 'generic':
            script_content = generate_generic_script(group['code'], temp_path)
        elif group.get('type') == 'revolve':
            # Revolve operation
            script_content = generate_cadquery_revolve_script(
                group['insts'],
                group['revolve_axis_start'],
                group['revolve_axis_end'],
                group['revolve_angle'],
                temp_path,
                **_revolve_frame(group)
            )
        else:
            # Extrude operation
            script_content = generate_cadquery_script([group['insts']], group['height'], temp_path)
        
        success = execute_cadquery_script(script_content, temp_path, script_path)
        
        if not success:
            return 0.0
            
        mesh = trimesh.load(temp_path, force='mesh')
        volume = 0.0
        if mesh is not None:
            volume = abs(mesh.volume)  # Use absolute value for consistency
        
        # Clean up temporary files
        try:
            import os
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            if os.path.exists(script_path):
                os.unlink(script_path)
        except:
            pass
        
        return volume
        
    except Exception as e:
        print(f"Failed to calculate volume for operation: {e}")
        return 0.0


def _cache_solids_enabled() -> bool:
    # Env so spawned pool workers see it (set by greedy_iou_based_pruning).
    return os.environ.get("CADFIT_CACHE_SOLIDS", "") not in ("", "0")


def _build_from_cached_solids(groups, stl_out):
    """Write the compound STL for `groups` by concatenating the per-candidate
    STLs built during evaluation, instead of rebuilding them in CadQuery.

    A CadQuery `.add()` compound exports each solid's triangulation
    independently, so the concatenation is triangle-for-triangle identical
    (verified on the benchmark parts). Returns False if any STL is missing."""
    paths = [g.get('stl_path') for g in groups]
    if not paths or not all(p and os.path.exists(p) for p in paths):
        return False
    try:
        meshes = [trimesh.load(p, force='mesh', process=False) for p in paths]
        trimesh.util.concatenate(meshes).export(stl_out)
        return os.path.exists(stl_out)
    except Exception as e:
        print(f"  Warning: cached-solid build failed ({e}); falling back to CadQuery")
        return False


def _exact_union_enabled() -> bool:
    return os.environ.get("CADFIT_EXACT_UNION", "") not in ("", "0")


def _groups_manifold(groups):
    """(union of add groups) - (union of cut groups), from cached candidate STLs."""
    import iou as _iou
    paths = [g.get('stl_path') for g in groups]
    if not paths or not all(p and os.path.exists(p) for p in paths):
        return None
    parts = [_iou._cached_manifold(p, normalize=False) for p in paths]
    if any(m is None for m in parts):
        return None
    adds = [m for m, g in zip(parts, groups) if g.get('op') != 'cut']
    cuts = [m for m, g in zip(parts, groups) if g.get('op') == 'cut']
    if not adds:
        return None
    try:
        M = _iou.manifold3d.Manifold
        union = M.batch_boolean(adds, _iou._OP_ADD) if len(adds) > 1 else adds[0]
        if cuts:
            tool = M.batch_boolean(cuts, _iou._OP_ADD) if len(cuts) > 1 else cuts[0]
            union = union - tool
    except Exception:
        return None
    return union


def _group_solid_code(group, name, tag):
    """Script lines that build one candidate group into variable `name`, with
    its internal variables renamed by `tag` so it can sit next to others."""
    import re
    if group.get('type') == 'generic':
        body = group['code'].replace('{N}', tag).split('\n')
        return body + [f"{name} = solid_gen_{tag}"]
    if group.get('type') == 'revolve':
        script = generate_cadquery_revolve_script(
            group['insts'], group['revolve_axis_start'], group['revolve_axis_end'],
            group['revolve_angle'], '/dev/null', **_revolve_frame(group))
    else:
        script = generate_cadquery_script_multi_height([group['insts']], [group['height']], '/dev/null')
    out = []
    for line in script.split('\n'):
        st = line.strip()
        if not st or st.startswith('import ') or 'cq.exporters.export' in st or st.startswith('print('):
            continue
        line = re.sub(r'\b(plane|sketch|solid|loop)_(\w+)', rf'\1_{tag}_\2', line)
        line = re.sub(r'\bresult\b', name, line)
        out.append(line)
    return out


def _beam_width() -> int:
    try:
        return int(os.environ.get("CADFIT_BEAM") or 0)
    except ValueError:
        return 0


def beam_search(cands, tools, gt_mesh, output_folder, width=4, max_depth=40, min_gain=1e-4,
                time_budget=240.0, add_min_inside=0.3, cut_max_inside=0.3, seed=None):
    """Beam search over compositions (adds, cuts), scored by exact manifold IoU.

    Greedy forward selection is path-dependent: one early candidate can lock
    the search into a worse optimum (see REPORT3 §5). Here the top-`width`
    partial models survive each depth. Moves are "add candidate", "cut
    tool" and "remove an add"; an add only qualifies if the candidate lies mostly inside the GT,
    a cut only if the tool lies mostly outside it. Each move's IoU is exact:
    I' = |M' ^ G|, V' = |M'| from one boolean on the current model. An upper
    bound (I + |c ^ G|) / |M v G| skips adds that cannot beat the parent.
    With `seed` (groups, cuts marked op='cut', e.g. the greedy result) the
    search starts from that model instead of the best single candidates.
    Returns (groups, iou) with cut groups marked op='cut'.
    """
    import iou as _iou
    t0 = time.time()
    gt_path = os.path.join(output_folder, '_greedy_gt_cached.stl')
    if not os.path.exists(gt_path):
        gt_mesh.copy().export(gt_path)
    G = _iou._cached_manifold(gt_path, normalize=True)
    if G is None:
        return None, None
    vG = abs(G.volume())

    def prep(groups, want_inside, force=False):
        out = []
        for g in groups:
            m = _iou._cached_manifold(g['stl_path'], normalize=False) if g.get('stl_path') else None
            if m is None:
                continue
            v = abs(m.volume())
            # A near-empty solid (e.g. a revolve of a degenerate profile)
            # adds nothing but can break the booleans of every state it joins.
            if v <= 1e-6 * vG:
                continue
            gi = abs((m ^ G).volume())
            if gi > min(v, vG) * (1 + 1e-6) + 1e-12:
                # Same broken-boolean signature as in state(): drop it here so
                # it cannot poison every state it would join.
                print(f"  Beam: dropping {g.get('sketch_id')} (|c^G| {gi:.5g} > min(|c| {v:.5g}, |G| {vG:.5g}))")
                continue
            frac = gi / v
            if force or (want_inside and frac >= add_min_inside) or (not want_inside and frac <= cut_max_inside):
                out.append({'g': g, 'm': m, 'v': v, 'gi': gi})
        return out

    A = prep(cands, True)
    T = prep(tools or [], False)
    if not A:
        return None, None

    def score(I, V):
        u = V + vG - I
        return I / u if u > 0 else 0.0

    union = _iou.manifold3d.Manifold.batch_boolean

    def state(adds, cuts, Madd, C, M=None):
        # A state's model is (union of adds) - (union of cuts): the geometry
        # the emitted groups build, whatever order the moves came in.
        if M is None:
            M = Madd - C if C is not None else Madd
        I, V = abs((M ^ G).volume()), abs(M.volume())
        # |M ^ G| above |M| or |G| means a boolean produced a broken manifold
        # (abs() hides an inverted shell); on raw ABC parts such states scored
        # IoU 9.73 (00001081) and 1.18 (00000456) and won. Never accept them.
        iou = score(I, V) if I <= min(V, vG) * (1 + 1e-6) + 1e-12 else -1.0
        return {'adds': adds, 'cuts': cuts, 'Madd': Madd, 'C': C, 'M': M, 'I': I, 'V': V, 'iou': iou}

    if seed:
        # Seed members that the inside/outside filters dropped still belong
        # to the seed model, so they are appended unfiltered.
        def index(pool, groups):
            ids = []
            for g in groups:
                k = next((k for k, x in enumerate(pool) if x['g'].get('stl_path') == g.get('stl_path')), None)
                if k is None:
                    extra = prep([g], True, force=True)
                    if not extra:
                        return None
                    pool.append(extra[0])
                    k = len(pool) - 1
                ids.append(k)
            return tuple(sorted(set(ids)))
        sa = index(A, [g for g in seed if g.get('op') != 'cut'])
        sc = index(T, [dict(g, op=None) for g in seed if g.get('op') == 'cut'])
        if not sa or sc is None:
            return None, None
        Madd = union([A[i]['m'] for i in sa], _iou._OP_ADD) if len(sa) > 1 else A[sa[0]]['m']
        C = (union([T[j]['m'] for j in sc], _iou._OP_ADD) if len(sc) > 1 else T[sc[0]]['m']) if sc else None
        beam = [state(sa, sc, Madd, C)]
        print(f"  Beam seed: IoU {beam[0]['iou']:.5f} ({len(sa)} adds, {len(sc)} cuts)")
        if beam[0]['iou'] < 0:
            s0 = beam[0]
            print(f"  Beam: seed boolean is broken (|M^G| {s0['I']:.5g}, |M| {s0['V']:.5g}, |G| {vG:.5g}); keeping greedy")
            return None, None
    else:
        # Initial beam: best single adds.
        beam = sorted(({'adds': (i,), 'cuts': (), 'Madd': a['m'], 'C': None, 'M': a['m'], 'I': a['gi'],
                        'V': a['v'], 'iou': score(a['gi'], a['v'])} for i, a in enumerate(A)),
                      key=lambda s: -s['iou'])[:width]
    best = beam[0]
    evals = 0
    for depth in range(max_depth):
        if time.time() - t0 > time_budget:
            print(f"  Beam: time budget reached at depth {depth}")
            break
        children = {}

        def offer(st, key, make):
            nonlocal evals
            # One state's moves can take minutes on dense parts (00001081 ran
            # 845 s against a 240 s budget), so the deadline is checked per move.
            if key in children or time.time() - t0 > time_budget:
                return
            evals += 1
            ch = make()
            if ch['iou'] > st['iou'] + min_gain:
                children[key] = ch

        for st in beam:
            U = st['V'] + vG - st['I']
            for i, a in enumerate(A):
                if i in st['adds']:
                    continue
                if (st['I'] + a['gi']) / U <= st['iou'] + min_gain:
                    continue  # cannot beat the parent even with zero overlap cost
                offer(st, (tuple(sorted(st['adds'] + (i,))), st['cuts']),
                      lambda: state(tuple(sorted(st['adds'] + (i,))), st['cuts'], st['Madd'] + a['m'], st['C']))
            for j, t in enumerate(T):
                if j in st['cuts']:
                    continue
                if abs((t['m'] ^ st['M']).volume()) < 1e-4 * st['V']:
                    continue
                offer(st, (st['adds'], tuple(sorted(st['cuts'] + (j,)))),
                      lambda: state(st['adds'], tuple(sorted(st['cuts'] + (j,))), st['Madd'],
                                    st['C'] + t['m'] if st['C'] is not None else t['m'], st['M'] - t['m']))
            # Removal lets the search back out of an early add that later ones
            # make redundant: a large, loose candidate often has the best
            # single IoU, seeds every beam state, and only hurts once the
            # parts it overhangs are covered by tighter candidates.
            if len(st['adds']) > 1:
                for i in st['adds']:
                    rest = tuple(k for k in st['adds'] if k != i)
                    offer(st, (rest, st['cuts']),
                          lambda: state(rest, st['cuts'],
                                        union([A[k]['m'] for k in rest], _iou._OP_ADD) if len(rest) > 1 else A[rest[0]]['m'],
                                        st['C']))
            if time.time() - t0 > time_budget:
                break
        if not children:
            break
        beam = sorted(children.values(), key=lambda s: -s['iou'])[:width]
        if beam[0]['iou'] > best['iou']:
            best = beam[0]
        print(f"  Beam depth {depth + 1}: best IoU {best['iou']:.5f} ({len(best['adds'])} adds, "
              f"{len(best['cuts'])} cuts), {len(children)} children, {evals} evals")

    adds, cuts, cur = list(best['adds']), list(best['cuts']), best['iou']
    log_event("prune_phase", phase="beam", duration=time.time() - t0, width=width, evals=evals,
              adds=len(adds), cuts=len(cuts), iou=float(cur))
    groups = [A[i]['g'] for i in adds] + [dict(T[j]['g'], op='cut') for j in cuts]
    return groups, cur


def _cut_phase_enabled() -> bool:
    return os.environ.get("CADFIT_CUT_PHASE", "") not in ("", "0")


def cut_phase(groups, pool, gt_mesh, output_folder, max_cuts=30, min_gain=1e-4,
              max_inside=0.3, time_budget=None):
    """Greedily subtract candidate solids from the selected model while IoU improves.

    Stock search only unions candidates, so a blind pocket or hole must be
    carved by the residual refinement pass (a full re-analysis of recon - GT).
    Here every evaluated candidate, including the ones dropped for near-zero
    IoU (a hole's own extrusion is empty space), is a potential cut tool: it
    qualifies if it removes material from the current model and lies mostly
    outside the ground truth. Returns (groups + accepted cuts, iou)."""
    import iou as _iou
    U = _groups_manifold(groups)
    gt_path = os.path.join(output_folder, '_greedy_gt_cached.stl')
    if not os.path.exists(gt_path):
        gt_mesh.copy().export(gt_path)
    G = _iou._cached_manifold(gt_path, normalize=True)
    if U is None or G is None:
        return groups, None
    vG = abs(G.volume())
    # Each round is three booleans per tool against the growing model; on raw
    # ABC 00000455 (116 revolve-heavy tools) four rounds took 45 min and the
    # greedy step hit its 3000 s timeout, losing the whole search. Past the
    # budget, keep the cuts accepted so far.
    if time_budget is None:
        time_budget = float(os.environ.get("CADFIT_CUT_BUDGET") or 300)
    deadline = time.time() + time_budget

    def iou_of(m):
        inter = abs((m ^ G).volume())
        if inter > min(abs(m.volume()), vG) * (1 + 1e-4):
            return -1.0  # inconsistent booleans: never accept
        return inter / (abs(m.volume()) + vG - inter)

    base = iou_of(U)
    t0 = time.time()
    tools = []
    out_of_time = False
    for c in pool:
        if time.time() > deadline:
            out_of_time = True
            break
        m = _iou._cached_manifold(c['stl_path'], normalize=False) if c.get('stl_path') else None
        if m is None:
            continue
        v = abs(m.volume())
        if v <= 0 or abs((m ^ G).volume()) / v > max_inside:
            continue
        tools.append((c, m))
    accepted = []
    while len(accepted) < max_cuts and tools and not out_of_time:
        best = None
        vU = abs(U.volume())
        for i, (c, m) in enumerate(tools):
            if time.time() > deadline:
                out_of_time = True  # a partial round's best still improves IoU
                break
            if abs((m ^ U).volume()) < 1e-4 * vU:
                continue
            cand = U - m
            gain = iou_of(cand) - base
            if gain > min_gain and (best is None or gain > best[0]):
                best = (gain, i, cand)
        if best is None:
            break
        gain, i, U = best
        base += gain
        c, _ = tools.pop(i)
        accepted.append(dict(c, op='cut'))
        print(f"  Cut phase: subtract {c.get('sketch_id')} ({c['type']}) gain={gain:.5f} -> IoU {base:.5f}")
    if out_of_time:
        print(f"  Cut phase: time budget ({time_budget:.0f}s) reached; keeping {len(accepted)} cuts")
    log_event("prune_phase", phase="cut", duration=time.time() - t0, pool=len(pool),
              tools=len(tools) + len(accepted), accepted=len(accepted), out_of_time=out_of_time)
    return groups + accepted, base


def _exact_union_iou(groups, gt_mesh, output_folder, filename_suffix):
    """IoU of the union of `groups` from their cached per-candidate STLs, with
    the union done exactly by manifold3d instead of concatenating the STLs and
    alpha-wrapping the self-overlapping compound on every call.

    Each candidate's manifold is built once and cached (iou._cached_manifold),
    so a forward/backward step costs one n-ary boolean plus one IoU boolean
    instead of an alpha-wrap of the whole growing model. Returns None if any
    candidate STL is missing or unusable (caller falls back to stock)."""
    import iou as _iou
    union = _groups_manifold(groups)
    if union is None:
        return None
    gt_path = os.path.join(output_folder, '_greedy_gt_cached.stl')
    if not os.path.exists(gt_path):
        gt_mesh.copy().export(gt_path)
    gt = _iou._cached_manifold(gt_path, normalize=True)
    if gt is None:
        return None
    vols = _iou._boolean_volumes(gt, union)
    if vols is None or vols[1] <= 0 or not _iou._volumes_consistent(gt, union, *vols):
        # A candidate mesh that is not a clean volume (e.g. a self-touching
        # loft) makes the booleans inconsistent; fall back to the stock path.
        return None
    out = union.to_mesh()
    trimesh.Trimesh(np.asarray(out.vert_properties)[:, :3], np.asarray(out.tri_verts),
                    process=False).export(f'{output_folder}/greedy_{filename_suffix}.stl')
    log_event("exact_union", n=len(groups))
    return vols[0] / vols[1]


def run_instruction_groups(groups, gt_mesh, output_folder, filename_suffix="tmp", alpha=0.01):
    """Helper function to build mesh from instruction groups and compute IoU.
    Handles both extrude and revolve operations."""
    if _exact_union_enabled() and _cache_solids_enabled():
        iou_val = _exact_union_iou(groups, gt_mesh, output_folder, filename_suffix)
        if iou_val is not None:
            executed = []
            for group in groups:
                executed.extend(group['insts'])
                if group.get('type') == 'generic':
                    executed.append(f"{group['kind']}()")
                elif group.get('type') == 'revolve':
                    executed.append(f"revolve(angle={group['revolve_angle']}, axis_start={group['revolve_axis_start']}, axis_end={group['revolve_axis_end']})")
                else:
                    executed.append(f"extrude(height={group['height']})")
            return iou_val, executed
    if any(g.get('op') == 'cut' for g in groups):
        print("  Cut groups need the exact-union path; ignoring cuts in this evaluation")
        groups = [g for g in groups if g.get('op') != 'cut']
    try:
        # Separate extrude and revolve operations
        extrude_groups = [g for g in groups if g.get('type') not in ('revolve', 'generic')]
        revolve_groups = [g for g in groups if g.get('type') == 'revolve']
        generic_groups = [g for g in groups if g.get('type') == 'generic']
        
        all_meshes = []

        for idx, group in enumerate(generic_groups):
            output_path = f'{output_folder}/greedy_{filename_suffix}_generic_{idx}'
            script_content = generate_generic_script(group['code'], f'{output_path}.stl')
            success = _build_from_cached_solids([group], f'{output_path}.stl')
            if not success:
                success = execute_cadquery_script(script_content, f'{output_path}.stl', f'{output_path}.py')
            if success:
                mesh = trimesh.load(f'{output_path}.stl', force='mesh')
                if mesh is not None:
                    all_meshes.append(mesh)
        
        # Process extrude operations
        if extrude_groups:
            sketch_actions_list = []
            heights = []
            
            for idx, group in enumerate(extrude_groups):
                sketch_actions_list.append(group['insts'])
                heights.append(group['height'])
                print(f"  Adding extrude sketch {idx} with height {group['height']:.3f}")
            
            output_path = f'{output_folder}/greedy_{filename_suffix}_extrude'
            script_content = generate_cadquery_script_multi_height(sketch_actions_list, heights, f'{output_path}.stl')
            
            script_path = f'{output_path}.py'
            success = False
            if _cache_solids_enabled():
                # Keep writing the script (downstream reads it); skip executing it.
                with open(script_path, 'w') as f:
                    f.write(script_content)
                success = _build_from_cached_solids(extrude_groups, f'{output_path}.stl')
                log_event("solid_cache", hit=success, n=len(extrude_groups))
            if not success:
                success = execute_cadquery_script(script_content, f'{output_path}.stl', script_path)
            
            if success:
                mesh = trimesh.load(f'{output_path}.stl', force='mesh')
                if mesh is not None:
                    all_meshes.append(mesh)
        
        # Process revolve operations (each separately for now)
        for idx, group in enumerate(revolve_groups):
            print(f"  Adding revolve sketch {idx} with angle {group['revolve_angle']}°")
            
            output_path = f'{output_folder}/greedy_{filename_suffix}_revolve_{idx}'
            script_content = generate_cadquery_revolve_script(
                group['insts'],
                group['revolve_axis_start'],
                group['revolve_axis_end'],
                group['revolve_angle'],
                f'{output_path}.stl',
                **_revolve_frame(group)
            )
            
            script_path = f'{output_path}.py'
            success = False
            if _cache_solids_enabled():
                with open(script_path, 'w') as f:
                    f.write(script_content)
                success = _build_from_cached_solids([group], f'{output_path}.stl')
                log_event("solid_cache", hit=success, n=1)
            if not success:
                success = execute_cadquery_script(script_content, f'{output_path}.stl', script_path)
            
            if success:
                mesh = trimesh.load(f'{output_path}.stl', force='mesh')
                if mesh is not None:
                    all_meshes.append(mesh)
        
        # Combine all meshes
        if not all_meshes:
            return 0.0, []
        
        if len(all_meshes) == 1:
            combined_mesh = all_meshes[0]
        else:
            # Union all meshes. trimesh's union has an `is_volume` precheck
            # that fails on non-watertight CadQuery STL exports; fall back to
            # concatenation (which keeps multi-solid composition working — IoU
            # will still be computed correctly downstream via mesh booleans).
            from iou import _alpha_wrap
            combined_mesh = _alpha_wrap(all_meshes[0])
            for mesh in all_meshes[1:]:
                mesh = _alpha_wrap(mesh)
                try:
                    combined_mesh = combined_mesh.union(mesh)
                except Exception as e:
                    print(f"  Warning: union failed ({e}); falling back to concatenate")
                    combined_mesh = trimesh.util.concatenate([combined_mesh, mesh])
        
        # Save combined mesh
        output_path = f'{output_folder}/greedy_{filename_suffix}'
        combined_mesh.export(f'{output_path}.stl')
        
        # Compute IoU. Reuse a stable path for the GT export so the manifold
        # cache in `iou.py` stays warm across the inner-loop calls.
        iou = 0.0
        if combined_mesh is not None:
            try:
                gt_path = os.path.join(output_folder, '_greedy_gt_cached.stl')
                if not os.path.exists(gt_path):
                    gt_mesh.copy().export(gt_path)
                iou = compute_iou(gt_path, f'{output_path}.stl')
            except Exception as e:
                iou = 0.0
                print(f"IoU computation failed: {e}")
        
        # Create executed actions list
        executed = []
        for group in groups:
            executed.extend(group['insts'])
            if group.get('type') == 'generic':
                executed.append(f"{group['kind']}()")
            elif group.get('type') == 'revolve':
                executed.append(f"revolve(angle={group['revolve_angle']}, axis_start={group['revolve_axis_start']}, axis_end={group['revolve_axis_end']})")
            else:
                executed.append(f"extrude(height={group['height']})")
        
        return iou, executed
        
    except Exception as e:
        print(f"Error in run_instruction_groups for {filename_suffix}: {e}")
        import traceback
        traceback.print_exc()
        return 0.0, []


def safe_pool_map(pool, fn, args, deadline=None, grace=600.0, stall=1800.0, poll=2.0):
    """`pool.map(fn, args)` that cannot block forever.

    A plain map() never returns if a task is lost: mp.Pool replaces a worker
    killed mid-task (OCP segfault, OOM killer) without returning its task, and
    a forked worker can deadlock on a lock held by a thread of the parent. On
    raw ABC parts the greedy step then sat idle until run_pipeline's 3000 s
    timeout, which discarded the finished search (00001387: 0.965) and left
    the pool orphaned. Give up on the remaining tasks when `grace` s pass
    without a task finishing after a worker died, when `stall` s pass without
    a task finishing at all, or at the absolute time `deadline`.
    Returns (results, lost): a lost or raising task's result is None. If
    lost > 0 the pool may hold stuck workers; terminate() it, do not join().
    """
    pending = [pool.apply_async(fn, (a,)) for a in args]
    pids = {p.pid for p in pool._pool}
    died, last_done, last_t = False, -1, time.time()
    while True:
        done = sum(r.ready() for r in pending)
        if done == len(pending):
            break
        now = time.time()
        if done != last_done:
            last_done, last_t = done, now
        if not died and {p.pid for p in pool._pool} != pids:
            died = True
            print(f"  ⚠️  A pool worker died; {len(pending) - done} task(s) unfinished")
        if (died and now - last_t > grace) or now - last_t > stall or (deadline and now > deadline):
            print(f"  ⚠️  Giving up on {len(pending) - done} unfinished pool task(s)")
            break
        next(r for r in pending if not r.ready()).wait(poll)
    results = []
    for r in pending:
        if not r.ready():
            results.append(None)
            continue
        try:
            results.append(r.get())
        except Exception as e:
            print(f"  ⚠️  Pool task raised {e!r}")
            results.append(None)
    return results, sum(x is None for x in results)


def abandon_pool(pool):
    """Stop `pool` without Pool.terminate(). terminate() takes the task queue's
    lock and waits for stop sentinels that a stuck pool never delivers; the
    greedy step then sat there until its 3000 s timeout and lost the search
    (abc60r 00002383, 00000572: stack dumps inside terminate() after the
    removal pass). Kill the workers instead; their results are already in."""
    from multiprocessing.pool import TERMINATE
    pool._state = TERMINATE
    pool._worker_handler._state = TERMINATE  # do not replace the killed workers
    pool._task_handler._state = TERMINATE
    try:
        pool._change_notifier.put(None)
    except Exception:
        pass
    pool._worker_handler.join(timeout=5)
    for p in list(pool._pool):
        try:
            p.kill()
        except Exception:
            pass
    for p in list(pool._pool):
        p.join(timeout=5)
    pool._terminate.cancel()  # its finalizer would run terminate() at exit


@contextlib.contextmanager
def guarded_pool(processes, **kw):
    """`with mp.Pool(...)` whose exit uses abandon_pool, not terminate()."""
    pool = mp.Pool(processes, **kw)
    try:
        yield pool
    finally:
        abandon_pool(pool)


def _test_removal_worker(args):
    """Worker function to test removal of a single extrusion."""
    idx, groups_before, groups_after, gt_mesh, output_folder, iteration, alpha = args
    try:
        test_groups = groups_before + groups_after
        suffix = f"removal_iter{iteration}_test{idx}"
        test_iou, _ = run_instruction_groups(test_groups, gt_mesh, output_folder, suffix, alpha)
        # Only the IoU is used. Each test leaves a full model STL (plus the
        # fallback path's per-type STL and script); on a raw ABC part with a
        # finely tessellated revolve, 20 removal rounds left 4414 files, 13 GB.
        for f in glob.glob(os.path.join(glob.escape(output_folder), f"greedy_{suffix}[._]*")):
            try:
                os.remove(f)
            except OSError:
                pass
        return idx, test_iou, None
    except Exception as e:
        return idx, None, str(e)


def greedy_iou_based_pruning(precomp, gt_mesh, output_folder="search", alpha=0.01, batch_removal=False, num_workers: int = 15,
                             fast_prune: bool = False, cache_volumes: bool = False,
                             persistent_pool: bool = False, cache_solids: bool = False, cut_pool=None,
                             order: str = 'ratio'):
    """
    Greedy pruning based on IoU values:
    1. Start with the extrusion having the highest individual IoU
    2. If IoU > 0.99, stop (near-perfect reconstruction)
    3. Otherwise, iteratively add the next best extrusion and check if IoU improves
    4. Keep only extrusions that increase the overall IoU
    5. Continue until no more extrusions improve the result
    
    Args:
        batch_removal: If True, remove all candidates with iou_gain > -0.005 in one batch
        fast_prune: If True, read a candidate's volume from the STL already built
            during evaluation (when that STL matches the candidate's actions)
            instead of re-running CadQuery, and reuse one worker pool for the
            whole removal loop. Intended to leave the selection unchanged.
    """
    import os, pickle, json
    cache_volumes = cache_volumes or fast_prune
    persistent_pool = persistent_pool or fast_prune
    if cache_solids:
        os.environ["CADFIT_CACHE_SOLIDS"] = "1"
    
    # Check if results already computed
    files_exist = all([
        os.path.exists(f'{output_folder}/greedy_instruction_groups.pkl'),
        os.path.exists(f'{output_folder}/greedy_keep_mask.json'),
        os.path.exists(f'{output_folder}/greedy_extrusion_data.json'),
        os.path.exists(f'{output_folder}/greedy_final_actions.pkl')
    ])
    if files_exist:
        print("Reloading greedy optimization results from disk...")
        with open(f'{output_folder}/greedy_instruction_groups.pkl', 'rb') as f:
            instruction_groups = pickle.load(f)
        with open(f'{output_folder}/greedy_keep_mask.json', 'r') as f:
            keep_mask = json.load(f)
        with open(f'{output_folder}/greedy_extrusion_data.json', 'r') as f:
            extrusion_data = json.load(f)
        with open(f'{output_folder}/greedy_final_actions.pkl', 'rb') as f:
            final_executed = pickle.load(f)
        
        # Rebuild final mesh
        final_groups = [g for k, g in enumerate(instruction_groups) if keep_mask[k]]
        final_iou, _ = run_instruction_groups(final_groups, gt_mesh, output_folder, "tmp", alpha)
        mesh_final = trimesh.load(f'{output_folder}/greedy_tmp.stl', force='mesh')
        print(f"Final IoU after greedy pruning (reloaded): {final_iou:.6f}")
        return final_iou, mesh_final, final_executed

    # Collect all best extrusions (positive and negative) with their individual IoUs
    # Also collect revolve operations if available
    # For each sketch, we'll add ALL valid operations (pos, neg, merged, revolve) and let greedy search pick the best
    extrusion_candidates = []
    for idx, sketch in enumerate(precomp):
        insts = sketch['insts']
        # Stock precomp is positional (list index == sketch index); the identity
        # fix carries the real index and a typed label instead.
        sketch_no = sketch.get('sketch_idx', idx)
        sketch_id = sketch.get('sketch_id', str(idx))
        
        # Add merged extrusion if available (takes precedence over individual pos/neg)
        if sketch.get('merged_h') is not None and sketch.get('merged_iou', 0.0) > 0:
            extrusion_candidates.append({
                'sketch_idx': sketch_no,
                'sketch_id': sketch_id,
                'insts': sketch['merged_insts'],
                'height': sketch['merged_h'],
                'individual_iou': sketch['merged_iou'],
                'type': 'merged'
            })
        else:
            # Add positive extrusion if available
            if sketch.get('pos_h') is not None and sketch.get('pos_iou', 0.0) > 0:
                extrusion_candidates.append({
                    'sketch_idx': sketch_no,
                    'sketch_id': sketch_id,
                    'insts': insts,
                    'height': sketch['pos_h'],
                    'individual_iou': sketch['pos_iou'],
                    'type': 'pos',
                    'stl_path': sketch.get('pos_stl')
                })
            
            # Add negative extrusion if available
            if sketch.get('neg_h') is not None and sketch.get('neg_iou', 0.0) > 0:
                extrusion_candidates.append({
                    'sketch_idx': sketch_no,
                    'sketch_id': sketch_id,
                    'insts': insts,
                    'height': sketch['neg_h'],
                    'individual_iou': sketch['neg_iou'],
                    'type': 'neg'
                })
        
        if sketch.get('generic'):
            g = sketch['generic']
            extrusion_candidates.append({
                'sketch_idx': sketch_no,
                'sketch_id': sketch_id,
                'insts': [],
                'height': 0,
                'individual_iou': g['iou'],
                'type': 'generic',
                'kind': g['kind'],
                'code': g['code'],
                'stl_path': g.get('stl'),
            })
            continue

        # Add revolve operation if available
        if sketch.get('revolve_angle') is not None and sketch.get('revolve_iou', 0.0) > 0:
            extrusion_candidates.append({
                'sketch_idx': sketch_no,
                'sketch_id': sketch_id,
                'insts': insts,
                'height': 0,
                'individual_iou': sketch['revolve_iou'],
                'type': 'revolve',
                'revolve_angle': sketch['revolve_angle'],
                'revolve_axis_start': sketch['revolve_axis_start'],
                'revolve_axis_end': sketch['revolve_axis_end'],
                'revolve_axis_angle': sketch.get('revolve_axis_angle'),
                'revolve_origin': sketch.get('revolve_origin'),
                'revolve_normal': sketch.get('revolve_normal'),
                'revolve_xdir': sketch.get('revolve_xdir'),
                'stl_path': sketch.get('revolve_stl')
            })

    for i, c in enumerate(extrusion_candidates):
        c['candidate_id'] = i

    if not extrusion_candidates:
        print("No valid extrusion candidates found!")
        return 0.0, None, []
    
    # Count and print number of each type
    num_revolve_cand = sum(1 for c in extrusion_candidates if c['type'] == 'revolve')
    num_extrude_cand = len(extrusion_candidates) - num_revolve_cand
    print(f"  - {num_extrude_cand} extrusion candidates")
    print(f"  - {num_revolve_cand} revolve candidates")

    # Calculate volumes for all candidates first
    print(f"Found {len(extrusion_candidates)} extrusion candidates, calculating volumes...")
    _t_phase = time.time()
    for i, candidate in enumerate(extrusion_candidates):
        try:
            stl_path = candidate.get('stl_path')
            if cache_volumes and stl_path and os.path.exists(stl_path):
                volume = abs(trimesh.load(stl_path, force='mesh').volume)
            else:
                volume = calculate_extrusion_volume(candidate)
            candidate['volume'] = volume
            print(f"  Candidate {i}: Sketch {candidate['sketch_idx']} ({candidate['type']}): IoU={candidate['individual_iou']:.6f}, h={candidate['height']:.3f}, vol={volume:.6f}")
        except Exception as e:
            print(f"  Candidate {i}: Volume calculation failed ({e}), using volume=0.0")
            candidate['volume'] = 0.0

    log_event("prune_phase", phase="volume_pass", duration=time.time() - _t_phase, n=len(extrusion_candidates))

    # Filter out candidates with negligible volume (< 1e-4) to avoid division by zero
    original_count = len(extrusion_candidates)
    extrusion_candidates = [c for c in extrusion_candidates if c['individual_iou'] >= 1e-2]
    filtered_count = original_count - len(extrusion_candidates)
    if filtered_count > 0:
        print(f"Filtered out {filtered_count} candidates with volume < 1e-4")

    if not extrusion_candidates:
        print("No valid extrusion candidates remaining after volume filtering!")
        return 0.0, None, []

    # Sort candidates by IoU/volume ratio (descending - best ratio first)
    # Forward-phase order. Stock: IoU/volume. Multi-start (greedy_search.py)
    # also tries individual IoU and volume, since the greedy is myopic and a
    # bigger candidate pool can lead it into a worse local optimum.
    if order == 'iou':
        extrusion_candidates.sort(key=lambda x: x['individual_iou'], reverse=True)
    elif order == 'volume':
        extrusion_candidates.sort(key=lambda x: x['volume'], reverse=True)
    else:
        extrusion_candidates.sort(key=lambda x: x['individual_iou'] / max(x['volume'], 1e-12), reverse=True)  # IoU/volume sort
    print(f"\nSorted {len(extrusion_candidates)} extrusion candidates by IoU")
    
    # Count and print number of each type
    num_revolve_cand = sum(1 for c in extrusion_candidates if c['type'] == 'revolve')
    num_extrude_cand = len(extrusion_candidates) - num_revolve_cand
    print(f"  - {num_extrude_cand} extrusion candidates")
    print(f"  - {num_revolve_cand} revolve candidates")
    
    print(f"\nTop 5 candidates:")
    for i, candidate in enumerate(extrusion_candidates[:5]):  # Show top 5
        if candidate['type'] == 'revolve':
            print(f"  {i+1}. Sketch {candidate['sketch_idx']} ({candidate['type']}): Volume={candidate['volume']:.6f}, IoU={candidate['individual_iou']:.6f}, angle={candidate['revolve_angle']}°")
        else:
            print(f"  {i+1}. Sketch {candidate['sketch_idx']} ({candidate['type']}): Volume={candidate['volume']:.6f}, IoU={candidate['individual_iou']:.6f}, h={candidate['height']:.3f}")

    # Greedy selection process
    selected_groups = []
    best_iou = 0.0
    early_stop = False

    print("\nStarting greedy selection process (testing from largest IoU to smallest)...")
    _t_phase = time.time()

    # Start with the largest IoU extrusion
    selected_groups.append(extrusion_candidates[0])
    current_iou, current_executed = run_instruction_groups(selected_groups, gt_mesh, output_folder, "greedy_step", alpha)
    best_iou = current_iou
    print(f"Step 1: Started with largest IoU extrusion (Volume={extrusion_candidates[0]['volume']:.6f}, IoU={extrusion_candidates[0]['individual_iou']:.6f})")
    print(f"        Combined IoU: {current_iou:.6f}")

    # Check if we already have near-perfect reconstruction
    if current_iou > 0.99:
        print(f"✓ IoU > 0.99 achieved with single extrusion ({current_iou:.6f}), stopping greedy selection")
        print(f"  Early stop: saving this single extrusion as best_greedy_parallel")
        final_groups = selected_groups
        early_stop = True
    else:
        # Iteratively try adding remaining extrusions (in order of decreasing volume)
        for i, candidate in enumerate(extrusion_candidates[1:], 2):
            print(f"\nStep {i}: Testing addition of sketch {candidate['sketch_idx']} ({candidate['type']}) with volume {candidate['volume']:.6f} (IoU {candidate['individual_iou']:.6f})")
        
            # Test with this candidate added
            test_groups = selected_groups + [candidate]
            try:
                test_iou, test_executed = run_instruction_groups(test_groups, gt_mesh, output_folder, "greedy_test", alpha)
            except Exception as e:
                print(f"        ✗ Error testing this extrusion: {e}")
                print(f"        Skipping sketch {candidate['sketch_idx']} ({candidate['type']})")
                continue
        
            print(f"        Combined IoU with this extrusion: {test_iou:.6f}")
        
            if test_iou >= best_iou:
                # Keep this extrusion
                selected_groups.append(candidate)
                best_iou = test_iou
                current_executed = test_executed
                print(f"        ✓ Kept extrusion (improvement: {test_iou - current_iou:.6f})")
                current_iou = test_iou
            
                # Check if we've reached near-perfect reconstruction
                if test_iou > 0.99:
                    print(f"        IoU > 0.99 achieved, stopping greedy selection")
                    break
            else:
                print(f"        ✗ Rejected extrusion (no improvement)")
    
        final_groups = selected_groups

    log_event("prune_phase", phase="forward", duration=time.time() - _t_phase,
              n=len(extrusion_candidates), selected=len(final_groups))
    _t_phase = time.time()
    print(f"\nGreedy selection completed:")
    print(f"  Selected {len(final_groups)} out of {len(extrusion_candidates)} extrusions")
    print(f"  Final IoU: {best_iou:.6f}")

    # Save this iou and number of operations to json for greedy_test
    with open(f'{output_folder}/greedy_iou_stats.json', 'w') as f:
        json.dump({
            'final_iou': best_iou,
            'num_extrusions': len(final_groups)
        }, f)

    # Post-processing: Iteratively remove extrusion that leads to biggest IoU increase
    # Skip post-processing if early stop (single extrusion with IoU > 0.99)
    if early_stop:
        print(f"\nSkipping post-processing: early stop with IoU > 0.99")
    elif len(final_groups) > 1:  # Only do post-processing if we have multiple extrusions
        print(f"\nStarting post-processing: iteratively removing extrusions that increase IoU...")


    if not early_stop and len(final_groups) > 1:  # Only do post-processing if we have multiple extrusions
        current_groups = final_groups.copy()
        current_iou = best_iou
        removed_count = 0
        iteration = 0
        shared_pool = mp.Pool(max(1, min(len(current_groups), num_workers))) if persistent_pool else None
    
        # Each round rebuilds the model once per selected extrusion, so on a
        # dense part with ~55 selected this pass alone overran the 3000 s
        # greedy step (raw ABC 00000456). Stop between rounds once the budget
        # is spent and keep the best selection so far; the slowest stock run
        # seen (1269 s) is well inside the default.
        backward_budget = float(os.environ.get("CADFIT_BACKWARD_BUDGET") or 1800)
        while len(current_groups) > 1:
            if time.time() - _t_phase > backward_budget:
                print(f"\n  Backward pass budget ({backward_budget:.0f}s) reached; keeping current selection")
                break
            iteration += 1
            print(f"\n  Iteration {iteration}: Testing removal of each of {len(current_groups)} extrusions in parallel...")
        
            # Prepare worker arguments for parallel removal testing
            worker_args = []
            for idx in range(len(current_groups)):
                groups_before = current_groups[:idx]
                groups_after = current_groups[idx+1:]
                worker_args.append((idx, groups_before, groups_after, gt_mesh, output_folder, iteration, alpha))
        
            # Test all removals in parallel (cap at num_workers).
            # A round may not outlive the budget: a stuck task used to hang
            # here until the greedy step's timeout threw the whole search away.
            deadline = _t_phase + backward_budget
            if shared_pool is not None:
                results, lost = safe_pool_map(shared_pool, _test_removal_worker, worker_args, deadline=deadline)
            else:
                with guarded_pool(max(1, min(len(worker_args), num_workers))) as pool:
                    results, lost = safe_pool_map(pool, _test_removal_worker, worker_args, deadline=deadline)
            if lost:
                print(f"  ✗ {lost} removal test(s) did not finish; keeping current selection")
                break
            batch_removal=False
            # Find best removal or collect all candidates for batch removal
            if batch_removal:
                # Batch removal: collect all candidates with iou_gain > -0.005
                candidates_to_remove = []
            
                for idx, test_iou, error in results:
                    if error is not None:
                        print(f"    ✗ Error testing removal of extrusion {idx}: {error}")
                        continue
                
                    if test_iou is None:
                        continue
                    iou_gain = (test_iou - current_iou)
                    group = current_groups[idx]
                    print(f"    Testing removal of extrusion {idx} (sketch {group['sketch_idx']}, type {group['type']}): IoU {current_iou:.6f} -> {test_iou:.6f} (gain: {iou_gain:.6f})")
                
                    # Collect all candidates with positive or near-zero IoU gain
                    if iou_gain > -0.005:
                        candidates_to_remove.append((idx, test_iou, iou_gain))
            
                # Remove all candidates in batch (from highest index to lowest to preserve indexing)
                if candidates_to_remove:
                    candidates_to_remove.sort(key=lambda x: x[0], reverse=True)
                    print(f"\n  Batch removing {len(candidates_to_remove)} extrusions with IoU gain > -0.02")
                
                    for idx, test_iou, iou_gain in candidates_to_remove:
                        removed_group = current_groups[idx]
                        print(f"    ✓ Removing extrusion {idx} (sketch {removed_group['sketch_idx']}, type {removed_group['type']}): IoU gain {iou_gain:.6f}")
                        current_groups = current_groups[:idx] + current_groups[idx+1:]
                        removed_count += 1
                
                    # Recompute IoU for the new configuration
                    if current_groups:
                        current_iou, _ = run_instruction_groups(current_groups, gt_mesh, output_folder, f"removal_iter{iteration}_batch", alpha)
                        print(f"  New IoU after batch removal: {current_iou:.6f}")
                    else:
                        print(f"  ✗ All extrusions removed, reverting to previous state")
                        break
                else:
                    print(f"  ✗ No candidates found for batch removal, stopping post-processing")
                    break
            else:
                # Original iterative approach: remove one at a time
                best_removal_idx = None
                best_removal_iou = current_iou
                best_iou_gain = -0.005
            
                for idx, test_iou, error in results:
                    if error is not None:
                        print(f"    ✗ Error testing removal of extrusion {idx}: {error}")
                        continue
                
                    if test_iou is None:
                        continue
                    iou_gain = (test_iou - current_iou)
                    group = current_groups[idx]
                    print(f"    Testing removal of extrusion {idx} (sketch {group['sketch_idx']}, type {group['type']}): IoU {current_iou:.6f} -> {test_iou:.6f} (gain: {iou_gain:.6f})")
                
                    # Track the removal that gives biggest IoU increase
                    if iou_gain >= best_iou_gain:
                        best_iou_gain = iou_gain
                        best_removal_idx = idx
                        best_removal_iou = test_iou
            
                # If we found a removal that increases IoU, apply it
                if best_removal_idx is not None and best_iou_gain > -0.005:
                    removed_group = current_groups[best_removal_idx]
                    current_groups = current_groups[:best_removal_idx] + current_groups[best_removal_idx+1:]
                    current_iou = best_removal_iou
                    removed_count += 1
                    print(f"  ✓ Removed extrusion {best_removal_idx} (sketch {removed_group['sketch_idx']}, type {removed_group['type']}): IoU improved by {best_iou_gain:.6f}")
                else:
                    # No removal improves IoU, stop iterating
                    print(f"  ✗ No removal improves IoU, stopping post-processing")
                    break
    
        if shared_pool is not None:
            abandon_pool(shared_pool)
        print(f"\n  Post-processing completed: removed {removed_count} out of {len(final_groups)} extrusions")
        print(f"  Final IoU after post-processing: {current_iou:.6f} (improvement: {current_iou - best_iou:.6f})")
    
        # Update final groups and IoU
        final_groups = current_groups
        best_iou = current_iou
    else:
        print("  Skipping post-processing: only one extrusion selected")



    log_event("prune_phase", phase="backward", duration=time.time() - _t_phase, selected=len(final_groups))

    if cut_pool and _cut_phase_enabled() and _exact_union_enabled() and _cache_solids_enabled():
        print(f"\nCut phase over {len(cut_pool)} candidate tools...")
        final_groups, cut_iou = cut_phase(final_groups, cut_pool, gt_mesh, output_folder)
    if _beam_width() and _exact_union_enabled() and _cache_solids_enabled():
        # Beam refines the greedy result rather than replacing it: it starts
        # from greedy's selection and only accepts improving moves, so it can
        # never end below greedy. Started from single candidates instead, it
        # lost 0.91 -> 0.72 on a part where the best single is a loose
        # oversized solid that seeds every state.
        print(f"\nBeam search (width {_beam_width()}) from the greedy selection over {len(extrusion_candidates)} candidates...")
        _beam_groups, _beam_iou = beam_search(extrusion_candidates, cut_pool if _cut_phase_enabled() else None,
                                              gt_mesh, output_folder, width=_beam_width(), seed=final_groups)
        if _beam_groups is not None:
            final_groups = _beam_groups
    # The stock keep_mask / 'selected' flags are not reliable, so record the selection here.
    log_event("prune_result", output_folder=output_folder,
              selected=[[g.get('sketch_id', g.get('sketch_idx')), g.get('type'), g.get('height'), g.get('individual_iou')]
                        for g in final_groups])

    # Build final mesh
    try:
        final_iou, final_executed = run_instruction_groups(final_groups, gt_mesh, output_folder, "tmp", alpha)
        final_mesh = trimesh.load(f'{output_folder}/greedy_tmp.stl', force='mesh')
    except Exception as e:
        print(f"Error building final mesh: {e}")
        final_iou = best_iou  # Use the last known good IoU
        final_mesh = None
        final_executed = []
    
    # Save results for future loading
    os.makedirs(output_folder, exist_ok=True)
    # Stock kept only {insts, height} here (so revolves reloaded as extrusions) and
    # gated keep_mask on `i < len(final_groups)` (so it was almost always False).
    instruction_groups = [{k: v for k, v in group.items() if k != 'stl_path'} for group in extrusion_candidates]
    selected_ids = {g['candidate_id'] for g in final_groups}
    keep_mask = [c['candidate_id'] in selected_ids for c in extrusion_candidates]
    
    with open(f'{output_folder}/greedy_instruction_groups.pkl', 'wb') as f:
        pickle.dump(instruction_groups, f)
    with open(f'{output_folder}/greedy_keep_mask.json', 'w') as f:
        json.dump(keep_mask, f)
    
    # Save extrusion data
    extrusion_data = []
    for i, candidate in enumerate(extrusion_candidates):
        extrusion_data.append({
            'candidate_idx': i,
            'candidate_id': candidate['candidate_id'],
            'sketch_idx': candidate['sketch_idx'],
            'sketch_id': candidate.get('sketch_id'),
            'height': candidate['height'],
            'individual_iou': candidate['individual_iou'],
            'type': candidate['type'],
            'selected': keep_mask[i]
        })
    
    with open(f'{output_folder}/greedy_extrusion_data.json', 'w') as f:
        json.dump(extrusion_data, f, indent=2)
    with open(f'{output_folder}/greedy_final_actions.pkl', 'wb') as f:
        pickle.dump(final_executed, f)
    
    # Save final IoU value
    final_iou_data = {
        'final_iou': float(final_iou),
        'num_selected_operations': len(final_groups),
        'num_total_candidates': len(extrusion_candidates)
    }
    with open(f'{output_folder}/greedy_final_iou.json', 'w') as f:
        json.dump(final_iou_data, f, indent=2)
    print(f"Saved final IoU ({final_iou:.6f}) to {output_folder}/greedy_final_iou.json")
    
    # Generate and save the final CadQuery script for best_greedy_parallel.stl
    try:
        # Separate extrude and revolve operations
        cut_groups = [g for g in final_groups if g.get('op') == 'cut']
        add_groups = [g for g in final_groups if g.get('op') != 'cut']
        extrude_groups = [g for g in add_groups if g.get('type') not in ('revolve', 'generic')]
        revolve_groups = [g for g in add_groups if g.get('type') == 'revolve']
        generic_groups = [g for g in add_groups if g.get('type') == 'generic']
        
        final_script_lines = ["import cadquery as cq", "import math", ""]
        solid_names = []

        for idx, group in enumerate(generic_groups):
            final_script_lines.append(f"# {group['kind'].capitalize()} operation {idx+1}")
            final_script_lines.extend(group['code'].replace('{N}', str(idx + 1)).split('\n'))
            final_script_lines.append("")
            solid_names.append(f"solid_gen_{idx+1}")
        
        # Generate extrude operations
        if extrude_groups:
            sketch_actions_list = []
            heights = []
            for group in extrude_groups:
                sketch_actions_list.append(group['insts'])
                heights.append(group['height'])
            
            # Generate multi-height script content
            extrude_script = generate_cadquery_script_multi_height(
                sketch_actions_list, 
                heights, 
                f'{output_folder}/best_greedy_parallel_extrude_only.stl'
            )
            # Extract the solid names and script body. Skip imports,
            # exports/prints, and the embedded `result = ...` / `result =
            # result.add(...)` lines — the outer composition block below
            # rebuilds those, so leaving them in produces duplicates.
            extrude_lines = extrude_script.split('\n')
            for line in extrude_lines:
                stripped = line.strip()
                if not stripped or stripped.startswith('import '):
                    continue
                if 'cq.exporters.export' in stripped or stripped.startswith('print('):
                    continue
                if stripped.startswith('result ='):
                    continue
                final_script_lines.append(line)
                if 'solid_' in line and '=' in line and 'extrude' in line:
                    solid_name = line.split('=')[0].strip()
                    if solid_name.startswith('solid_'):
                        solid_names.append(solid_name)
        
        # Generate revolve operations
        for idx, group in enumerate(revolve_groups):
            final_script_lines.append("")
            final_script_lines.append(f"# Revolve operation {idx+1}")
            
            revolve_script = generate_cadquery_revolve_script(
                group['insts'],
                group['revolve_axis_start'],
                group['revolve_axis_end'],
                group['revolve_angle'],
                f'{output_folder}/revolve_{idx}.stl',
                **_revolve_frame(group)
            )
            
            # Extract the revolve body, rename result to solid_revolve_N
            revolve_lines = revolve_script.split('\n')
            for line in revolve_lines:
                if line and not line.startswith('import ') and 'export' not in line and 'print(' not in line:
                    # Replace 'result = ' with 'solid_revolve_N = '
                    if line.strip().startswith('result = '):
                        solid_name = f"solid_revolve_{idx+1}"
                        line = line.replace('result = ', f'{solid_name} = ')
                        solid_names.append(solid_name)
                    final_script_lines.append(line)
        
        # Compose the final result. No exporter line in the saved script —
        # callers consume the sibling STL on disk or export themselves.
        final_script_lines.append("")
        if len(solid_names) > 1:
            final_script_lines.append(f"result = {solid_names[0]}")
            # `.add()` produces a Compound (Boolean-free, geometry-correct).
            # The pipeline cleans the exported STL via manifold3d downstream.
            for solid_name in solid_names[1:]:
                final_script_lines.append(f"result = result.add({solid_name})")
        elif len(solid_names) == 1:
            final_script_lines.append(f"result = {solid_names[0]}")

        for idx, group in enumerate(cut_groups):
            final_script_lines.append("")
            final_script_lines.append(f"# Cut operation {idx+1}")
            final_script_lines.extend(_group_solid_code(group, f"cut_{idx+1}", f"c{idx+1}"))
            final_script_lines.append(f"result = result.cut(cut_{idx+1})")
        
        # Save the final script
        final_script_path = f'{output_folder}/best_greedy_parallel.py'
        with open(final_script_path, 'w') as f:
            f.write('\n'.join(final_script_lines))
        print(f"Saved final CadQuery script to {final_script_path}")

        # Delete all files starting with 'adaptive_' and 'temp_' in the folder
        try:
            for pattern in ['adaptive_*', 'temp_*']:
                for filepath in glob.glob(os.path.join(output_folder, pattern)):
                    try:
                        os.unlink(filepath)
                    except Exception as e:
                        print(f"Warning: Failed to delete {filepath}: {e}")
        except Exception as e:
            print(f"Warning: Failed to clean up temporary files: {e}")


    except Exception as e:
        print(f"Warning: Failed to save final CadQuery script: {e}")
    
    return final_iou, final_mesh, final_executed


def run_search(loops_json: str, ground_truth: str, num_workers: int = 4,
               hmin: float = 1.0, hmax: float = 20.0, alpha_height: float = 0.01, alpha_greedy: float = 0.01, normalize: bool = False, revolve_json: str = None, merge_pos_neg: bool = False, batch_removal: bool = False, output_base_dir: str = "search_greedy_parallel"):
    """
    Run parallel CAD sketch optimization.
    
    Args:
        loops_json: Path to loops JSON file
        ground_truth: Path to ground truth STL file
        num_workers: Number of worker processes
        hmin: Minimum height range
        hmax: Maximum height range
        alpha_height: Alpha parameter for height search IoU computation
        alpha_greedy: Alpha parameter for greedy pruning IoU computation
        revolve_json: Path to JSON file with unsplit axis sketches for revolve detection
        merge_pos_neg: If True, merge pos and neg heights into single extrusion with translated origin
        batch_removal: If True, remove all candidates with iou_gain > -0.005 in one batch during post-processing
    """
    start_time = time.time()
    
    # Extract filename without extension from ground_truth path for output folder
    import os
    stl_filename = os.path.basename(ground_truth)
    output_folder = os.path.splitext(stl_filename)[0]  # Remove .stl extension
    # Add output_base_dir/
    output_folder = os.path.join(output_base_dir, output_folder)
    print(f"Using output folder: {output_folder}")
    
    with open(loops_json, 'r') as f:
        data = json.load(f)
    
    # Load revolve data if provided (unsplit axis sketches)
    revolve_data = None
    if revolve_json is not None:
        try:
            with open(revolve_json, 'r') as f:
                revolve_data = json.load(f)
            print(f"Loaded {len(revolve_data)} unsplit axis sketches from {revolve_json} for revolve detection")
        except Exception as e:
            print(f"Warning: Failed to load revolve_json {revolve_json}: {e}")
            revolve_data = None
    gt_mesh = trimesh.load(ground_truth, force='mesh')
    if normalize:
        gt_mesh = normalize_mesh(gt_mesh)

    n = len(data)
    if n == 0:
        print('no sketches')
        return None

    print(f'Precomputing per-sketch heights for {n} sketches using {num_workers} workers...')
    precomp_start_time = time.time()
    precomp = precompute_sketch_heights_parallel(data, gt_mesh, hmin, hmax, 
                                               num_workers=num_workers, 
                                               output_folder=output_folder, 
                                               alpha=alpha_height,
                                               revolve_data=revolve_data,
                                               merge_pos_neg=merge_pos_neg)
    precomp_end_time = time.time()
    precomp_duration = precomp_end_time - precomp_start_time
    print(f'Parallel precomputation completed in {precomp_duration:.2f} seconds')

    print('Running greedy IoU-based pruning...')
    greedy_start_time = time.time()
    final_iou, final_mesh, final_actions = greedy_iou_based_pruning(precomp, gt_mesh, 
                                                                   output_folder=output_folder, 
                                                                   alpha=alpha_greedy,
                                                                   batch_removal=batch_removal)
    greedy_end_time = time.time()
    greedy_duration = greedy_end_time - greedy_start_time
    print(f'Greedy pruning completed in {greedy_duration:.2f} seconds')
    
    total_duration = time.time() - start_time
    print(f'Total parallel search time: {total_duration:.2f} seconds')
    print(f'  - Parallel Precomputation: {precomp_duration:.2f}s ({precomp_duration/total_duration*100:.1f}%)')
    print(f'  - Greedy Pruning: {greedy_duration:.2f}s ({greedy_duration/total_duration*100:.1f}%)')
    
    print(f'Final best IoU={final_iou:.6f}')
    if final_mesh is not None:
        try:
            os.makedirs(output_folder, exist_ok=True)
            final_mesh.export(f'{output_folder}/best_greedy_parallel.stl')
            print(f'Saved mesh to {output_folder}/best_greedy_parallel.stl')
        except Exception as e:
            print('Failed to save mesh:', e)
    
    try:
        with open(f'{output_folder}/best_greedy_parallel_actions.txt', 'w') as f:
            f.write('actions = [\n')
            for a in final_actions:
                if isinstance(a, str):
                    f.write(f'    "{a}",\n')
                else:
                    cls = a.__class__.__name__
                    attrs = getattr(a, '__dict__', None)
                    if attrs:
                        parts = [f"{k}={repr(v)}" for k, v in attrs.items()]
                        f.write('    ' + cls + '(' + ', '.join(parts) + '),\n')
                    else:
                        f.write('    ' + repr(a) + ',\n')
            f.write(']\n')
        print(f'Saved actions to {output_folder}/best_greedy_parallel_actions.txt')
    except Exception as e:
        print('Failed to save actions:', e)

    # Save timing information
    try:
        timing_data = {
            'total_duration': total_duration,
            'precomputation_duration': precomp_duration,
            'greedy_duration': greedy_duration,
            'precomputation_percentage': precomp_duration/total_duration*100,
            'greedy_percentage': greedy_duration/total_duration*100,
            'num_workers': num_workers,
            'parallel': True,
            'alpha_height': alpha_height,
            'alpha_greedy': alpha_greedy
        }
        with open(f'{output_folder}/timing_summary_parallel.json', 'w') as f:
            json.dump(timing_data, f, indent=2)
        print(f'Saved timing summary to {output_folder}/timing_summary_parallel.json')
    except Exception as e:
        print('Failed to save timing summary:', e)

    return {
        'best_iou': final_iou,
        'mesh': final_mesh,
        'actions': final_actions,
        'num_extrusions': sum(1 for action in final_actions if "extrude" in str(action).lower()),
        'timing': {
            'total_duration': total_duration,
            'precomputation_duration': precomp_duration,
            'greedy_duration': greedy_duration
        },
        'num_workers': num_workers,
        'alpha_height': alpha_height,
        'alpha_greedy': alpha_greedy
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Parallel CAD sketch extrusion optimization with greedy IoU-based pruning')
    parser.add_argument('loops_json')
    parser.add_argument('ground_truth')
    parser.add_argument('--hmin', type=float, default=-2.1)
    parser.add_argument('--hmax', type=float, default=2.1)
    parser.add_argument('--alpha-height', type=float, default=0.01, help='Alpha parameter for height search IoU computation (default: 0.01)')
    parser.add_argument('--alpha-greedy', type=float, default=0.01, help='Alpha parameter for greedy pruning IoU computation (default: 0.01)')
    parser.add_argument('--alpha', type=float, default=None, help='Alpha parameter for both phases (overrides --alpha-height and --alpha-greedy if provided)')
    parser.add_argument('--num-workers', type=int, default=4, help='Number of worker processes (default: 4)')
    parser.add_argument('--normalize', default=False, action='store_true', help='Normalize meshes before processing (not implemented)')
    parser.add_argument('--revolve-json', type=str, default=None, help='JSON file with unsplit axis sketches for revolve detection')
    parser.add_argument('--merge-pos-neg', default=False, action='store_true', help='Merge positive and negative extrusions into single extrusion with translated origin')
    parser.add_argument('--batch-removal', default=False, action='store_true', help='Remove all candidates with IoU gain > -0.005 in one batch during post-processing (faster but less precise)')
    args = parser.parse_args()

    # Handle alpha parameter logic
    if args.alpha is not None:
        # If --alpha is provided, use it for both phases
        alpha_height = args.alpha
        alpha_greedy = args.alpha
        print(f"Using alpha={args.alpha} for both height search and greedy pruning")
    else:
        # Use separate alpha parameters
        alpha_height = args.alpha_height
        alpha_greedy = args.alpha_greedy
        print(f"Using alpha_height={alpha_height} for height search, alpha_greedy={alpha_greedy} for greedy pruning")

    run_search(args.loops_json, args.ground_truth, num_workers=args.num_workers, 
               hmin=args.hmin, hmax=args.hmax, alpha_height=alpha_height, alpha_greedy=alpha_greedy, 
               normalize=args.normalize, revolve_json=args.revolve_json, merge_pos_neg=args.merge_pos_neg,
               batch_removal=args.batch_removal)
#!/usr/bin/env python3
"""
split_loops.py

Read a `loops.json` file containing sketches of the form:
[
  { "origin": [...], "normal": [...], "xdir": [...], "loops": [ [ ... ], [ ... ] ] },
  ...
]

By default this script "splits" sketches so that every output entry contains exactly one loop
(i.e. every loop from the input becomes a separate sketch entry with the same origin, normal, and xdir).

Optional `--merge` mode will group loops that share the same origin, normal, and xdir into the same
sketch entry (uses rounding to decide equality, controlled by --decimals).

NEW: `--group-contained` mode will detect when loops are contained within other loops and keep
them together as one group. This is useful for sketch profiles with holes or inner contours.

The script now preserves the `xdir` field from the input JSON, which provides the x-direction
of the plane coordinate system alongside the origin and normal.

Usage:
  python split_loops.py loops.json --out loops_split.json
  python split_loops.py planar_contours.json --group-contained
  python split_loops.py loops.json --merge

"""
from __future__ import annotations
import json
import os
import argparse
from collections import defaultdict
from typing import Tuple, List
import numpy as np
from shapely.geometry import Polygon, Point
from shapely.errors import TopologicalError
import warnings
warnings.filterwarnings('ignore', category=RuntimeWarning)


def key_from_origin_normal_xdir(origin: List[float], normal: List[float], xdir: List[float], decimals: int = 6) -> Tuple:
    """Make a hashable key for grouping using rounded floats."""
    return (tuple(round(float(x), decimals) for x in origin) + 
            tuple(round(float(x), decimals) for x in normal) + 
            tuple(round(float(x), decimals) for x in xdir))


def project_loop_to_2d(loop_3d: List[List[float]], origin: List[float], normal: List[float], xdir: List[float] = None) -> List[Tuple[float, float]]:
    """Project a 3D loop onto the 2D plane defined by origin and normal."""
    # Convert to numpy arrays
    origin = np.array(origin)
    normal = np.array(normal)
    normal = normal / np.linalg.norm(normal)  # normalize
    
    if xdir is not None:
        # Use provided xdir
        u = np.array(xdir)
        u = u / np.linalg.norm(u)  # normalize
    else:
        # Create orthonormal basis for the plane
        # Choose an arbitrary vector not parallel to normal
        if abs(normal[0]) < 0.9:
            u = np.array([1.0, 0.0, 0.0])
        else:
            u = np.array([0.0, 1.0, 0.0])
        
        # Make u orthogonal to normal
        u = u - np.dot(u, normal) * normal
        u = u / np.linalg.norm(u)
    
    # Create second basis vector
    v = np.cross(normal, u)
    
    # Project each point
    projected = []
    for point_3d in loop_3d:
        point = np.array(point_3d)
        # Translate to origin
        relative = point - origin
        # Project onto plane
        x = np.dot(relative, u)
        y = np.dot(relative, v)
        projected.append((x, y))
    
    return projected


def is_loop_contained_in_loop(inner_loop: List[List[float]], outer_loop: List[List[float]], 
                              origin: List[float], normal: List[float], xdir: List[float] = None, tolerance: float = 1e-6) -> bool:
    """Check if inner_loop is contained within outer_loop."""
    try:
        # Project both loops to 2D
        inner_2d = project_loop_to_2d(inner_loop, origin, normal, xdir)
        outer_2d = project_loop_to_2d(outer_loop, origin, normal, xdir)
        
        # Create polygons (ensure they're closed)
        if len(inner_2d) < 3 or len(outer_2d) < 3:
            return False
            
        # Close loops if not already closed
        if inner_2d[0] != inner_2d[-1]:
            inner_2d.append(inner_2d[0])
        if outer_2d[0] != outer_2d[-1]:
            outer_2d.append(outer_2d[0])
        
        # Create shapely polygons
        try:
            outer_poly = Polygon(outer_2d)
            inner_poly = Polygon(inner_2d)
            
            # Make sure polygons are valid
            if not outer_poly.is_valid:
                outer_poly = outer_poly.buffer(0)
            if not inner_poly.is_valid:
                inner_poly = inner_poly.buffer(0)
            
            # Check if inner loop is contained within outer loop
            # We check if the inner polygon is within the outer polygon
            return outer_poly.contains(inner_poly) or outer_poly.covers(inner_poly)
            
        except (TopologicalError, ValueError) as e:
            # Fallback: check if most points of inner loop are inside outer polygon
            try:
                outer_poly = Polygon(outer_2d)
                if not outer_poly.is_valid:
                    outer_poly = outer_poly.buffer(0)
                
                inside_count = 0
                for point in inner_2d[:-1]:  # Skip the duplicate closing point
                    if outer_poly.contains(Point(point)):
                        inside_count += 1
                
                # Consider contained if most points (>80%) are inside
                return inside_count / len(inner_2d[:-1]) > 0.8
            except:
                return False
                
    except Exception as e:
        print(f"Warning: Failed to check containment: {e}")
        return False


def _loop_polygon(loop, origin, normal, xdir):
    """The polygon is_loop_contained_in_loop builds for `loop` (closed,
    buffer(0) if invalid), or None where it would raise."""
    try:
        pts = project_loop_to_2d(loop, origin, normal, xdir)
        if len(pts) < 3:
            return None
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        poly = Polygon(pts)
        return poly if poly.is_valid else poly.buffer(0)
    except Exception:
        return None


def group_contained_loops(loops: List[List[List[float]]], origin: List[float], normal: List[float], xdir: List[float] = None) -> List[List[List[List[float]]]]:
    """Group loops where some are contained within others."""
    if len(loops) <= 1:
        return [[loop] for loop in loops]

    # The pairwise test re-projected and rebuilt both polygons per pair; on
    # raw ABC parts (loops of thousands of points, 484 MB of sketches for
    # 00000456) that ran past the pipeline's timeout. Build each once.
    polys = [_loop_polygon(loop, origin, normal, xdir) for loop in loops]

    def contained(j, i):
        inner, outer = polys[j], polys[i]
        if inner is None or outer is None:
            return is_loop_contained_in_loop(loops[j], loops[i], origin, normal, xdir)
        try:
            if not inner.is_empty and not outer.is_empty:
                a, b = inner.bounds, outer.bounds
                if a[0] < b[0] or a[1] < b[1] or a[2] > b[2] or a[3] > b[3]:
                    return False  # covers() needs the inner box inside the outer
            return outer.contains(inner) or outer.covers(inner)
        except Exception:
            return is_loop_contained_in_loop(loops[j], loops[i], origin, normal, xdir)
    
    # Calculate areas to help determine outer vs inner loops
    loop_areas = []
    for loop in loops:
        try:
            projected = project_loop_to_2d(loop, origin, normal, xdir)
            if len(projected) >= 3:
                # Close loop if needed
                if projected[0] != projected[-1]:
                    projected.append(projected[0])
                poly = Polygon(projected)
                if poly.is_valid:
                    loop_areas.append(abs(poly.area))
                else:
                    loop_areas.append(0)
            else:
                loop_areas.append(0)
        except:
            loop_areas.append(0)
    
    # Sort loops by area (largest first - these are likely outer loops)
    loop_indices = list(range(len(loops)))
    loop_indices.sort(key=lambda i: loop_areas[i], reverse=True)
    
    groups = []
    used_indices = set()
    
    for i in loop_indices:
        if i in used_indices:
            continue
            
        # Start a new group with this loop as the potential outer loop
        current_group = [loops[i]]
        current_group_indices = [i]
        used_indices.add(i)
        
        # Find all loops contained within this one
        for j in loop_indices:
            if j in used_indices or j == i:
                continue
                
            # Check if loop j is contained in loop i
            if contained(j, i):
                current_group.append(loops[j])
                current_group_indices.append(j)
                used_indices.add(j)
        
        # Sort the group by area (largest first) to ensure consistent ordering
        if len(current_group) > 1:
            # Create pairs of (area, loop) and sort by area descending
            group_with_areas = [(loop_areas[idx], loops[idx]) for idx in current_group_indices]
            group_with_areas.sort(key=lambda x: x[0], reverse=True)
            current_group = [loop for area, loop in group_with_areas]
        
        groups.append(current_group)
    
    # Handle any remaining ungrouped loops
    for i in range(len(loops)):
        if i not in used_indices:
            groups.append([loops[i]])
    
    return groups


def compute_loop_area(loop: List[List[float]], origin: List[float], normal: List[float], xdir: List[float] = None) -> float:
    """Compute the area of a 3D loop by projecting to 2D."""
    try:
        projected = project_loop_to_2d(loop, origin, normal, xdir)
        if len(projected) >= 3:
            # Close loop if needed
            if projected[0] != projected[-1]:
                projected.append(projected[0])
            poly = Polygon(projected)
            if poly.is_valid:
                return abs(poly.area)
    except:
        pass
    return 0.0


def split_loops(input_path: str, output_path: str, merge: bool = False, group_contained: bool = False, decimals: int = 6):
    with open(input_path, 'r') as f:
        data = json.load(f)

    total_sketches = len(data)
    total_loops = 0
    out_entries = []

    if group_contained:
        # Group loops where some are contained within others
        for entry in data:
            origin = entry.get('origin')
            normal = entry.get('normal')
            xdir = entry.get('xdir')
            loops = entry.get('loops_3d', []) or []
            total_loops += len(loops)
            
            if len(loops) == 0:
                continue
            elif len(loops) == 1:
                # Single loop, just add it with area
                loop_area = compute_loop_area(loops[0], origin, normal, xdir)
                # Skip loops with area < 0.001
                if loop_area < 0.001:
                    continue
                entry_out = {
                    'origin': origin,
                    'normal': normal,
                    'loops_3d': loops,
                    'loop_areas': [loop_area]
                }
                if 'xdir' in entry and xdir is not None:
                    entry_out['xdir'] = xdir
                out_entries.append(entry_out)
            else:
                # Multiple loops - group contained ones
                loop_groups = group_contained_loops(loops, origin, normal, xdir)
                for group in loop_groups:
                    # Compute area for each loop in the group
                    group_areas = [compute_loop_area(loop, origin, normal, xdir) for loop in group]
                    # Filter out loops with area < 0.001
                    filtered_group = [(loop, area) for loop, area in zip(group, group_areas) if area >= 0.001]
                    if not filtered_group:
                        continue
                    filtered_loops = [loop for loop, area in filtered_group]
                    filtered_areas = [area for loop, area in filtered_group]
                    entry_out = {
                        'origin': origin,
                        'normal': normal,
                        'loops_3d': filtered_loops,
                        'loop_areas': filtered_areas
                    }
                    if 'xdir' in entry and xdir is not None:
                        entry_out['xdir'] = xdir
                    out_entries.append(entry_out)
                    
    elif merge:
        groups = defaultdict(list)  # key -> list of loops
        meta = {}  # key -> (origin, normal, xdir)
        for entry in data:
            origin = entry.get('origin')
            normal = entry.get('normal')
            xdir = entry.get('xdir')
            loops = entry.get('loops_3d', []) or []
            for loop in loops:
                total_loops += 1
                k = key_from_origin_normal_xdir(origin, normal, xdir or [0, 0, 0], decimals)
                groups[k].append(loop)
                if k not in meta:
                    meta[k] = (origin, normal, xdir)
        for k, loops in groups.items():
            origin, normal, xdir = meta[k]
            loop_areas = [compute_loop_area(loop, origin, normal, xdir) for loop in loops]
            # Filter out loops with area < 0.001
            filtered = [(loop, area) for loop, area in zip(loops, loop_areas) if area >= 0.001]
            if not filtered:
                continue
            filtered_loops = [loop for loop, area in filtered]
            filtered_areas = [area for loop, area in filtered]
            entry_out = {
                'origin': origin,
                'normal': normal,
                'loops_3d': filtered_loops,
                'loop_areas': filtered_areas
            }
            if xdir is not None:
                entry_out['xdir'] = xdir
            out_entries.append(entry_out)
    else:
        # split each loop into its own sketch entry
        for entry in data:
            origin = entry.get('origin')
            normal = entry.get('normal')
            xdir = entry.get('xdir')
            loops = entry.get('loops_3d', []) or []
            for loop in loops:
                total_loops += 1
                loop_area = compute_loop_area(loop, origin, normal, xdir)
                # Skip loops with area < 0.001
                if loop_area < 0.001:
                    continue
                entry_out = {
                    'origin': origin,
                    'normal': normal,
                    'loops_3d': [loop],
                    'loop_areas': [loop_area]
                }
                if 'xdir' in entry and xdir is not None:
                    entry_out['xdir'] = xdir
                out_entries.append(entry_out)

    # write output
    # Write-then-rename: a caller that kills this script on timeout must never
    # find a truncated JSON at output_path.
    tmp_path = output_path + '.tmp'
    with open(tmp_path, 'w') as f:
        json.dump(out_entries, f, indent=2)
    os.replace(tmp_path, output_path)

    mode_str = "group-contained" if group_contained else ("merge" if merge else "split")
    print(f"Read {total_sketches} sketch entries from {input_path}")
    print(f"Discovered {total_loops} total loops")
    print(f"Wrote {len(out_entries)} entries to {output_path} (mode: {mode_str})")
    
    if group_contained:
        # Print some statistics about grouping
        single_loop_entries = sum(1 for entry in out_entries if len(entry['loops_3d']) == 1)
        multi_loop_entries = len(out_entries) - single_loop_entries
        print(f"  - {single_loop_entries} entries with single loops")
        print(f"  - {multi_loop_entries} entries with grouped loops")


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Split loops.json into per-loop sketch entries, merge by origin+normal, or group contained loops')
    p.add_argument('input', help='input loops.json file')
    p.add_argument('--out', '-o', default='loops_split.json', help='output file path')
    p.add_argument('--merge', action='store_true', help='merge loops that share same origin+normal instead of splitting')
    p.add_argument('--group-contained', action='store_true', help='group loops where some are contained within others (e.g., holes)')
    p.add_argument('--decimals', type=int, default=6, help='decimals to round origin/normal when merging')
    args = p.parse_args()
    
    if args.merge and args.group_contained:
        print("Error: Cannot use both --merge and --group-contained options simultaneously")
        exit(1)
    
    split_loops(args.input, args.out, merge=args.merge, group_contained=args.group_contained, decimals=args.decimals)

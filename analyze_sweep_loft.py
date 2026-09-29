#!/usr/bin/env python3
"""
Propose loft and sweep candidates by tracking cross-sections through the mesh.

Stock CADFit only proposes extrusions (constant section along a straight line)
and revolves. Starting from each single-loop sketch, we march a section plane
through the mesh, following the nearest loop at each step:

  straight tracking (plane normal fixed): if the section changes shape or size
      along the way, the solid is a *loft* through keyframe sections;
  bent tracking (plane re-aimed at the new section centroid each step): if the
      centroid path turns, the solid is a *sweep* of the start profile along
      the centroid path (and, as a second candidate, a loft through the tilted
      sections, which also covers profiles that change along a curved path).

Sections that stay constant along a straight line are left to the extrusion
path. Ends are refined by bisection to where the section vanishes, so the
solids reach the caps instead of stopping a step short.

Output: sweep_loft_candidates.json, a list of generic candidates
  {kind, seed_idx, sections | profile+path, code, ...}
where `code` defines `solid_gen_{N}` (a cq.Workplane) with `{N}` left for the
caller to fill in, so candidates compose in the final script.

Usage:
  python analyze_sweep_loft.py loops_split.json mesh.stl --out sweep_loft_candidates.json [--normalize]
"""
import argparse
import json
import sys

import numpy as np
import trimesh

from iou import normalize_mesh

M_PTS = 48          # points per resampled section
STEP = 0.04         # tracking step in the normalized [-1,1] frame
MAX_STEPS = 80
AREA_JUMP = (0.6, 1.6)
MIN_REL_VAR = 0.03  # below this relative shape change, a straight track is a plain extrusion
MIN_TURN_DEG = 12.0
MAX_SEEDS = 40


# ---------------------------------------------------------------- geometry

def _frame(normal):
    n = np.asarray(normal, float)
    n = n / np.linalg.norm(n)
    a = np.array([0, 0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0, 0])
    u = np.cross(n, a)
    u /= np.linalg.norm(u)
    return n, u, np.cross(n, u)


def _poly_area_centroid(p2):
    x, y = p2[:, 0], p2[:, 1]
    x1, y1 = np.roll(x, -1), np.roll(y, -1)
    cr = x * y1 - x1 * y
    a = 0.5 * cr.sum()
    if abs(a) < 1e-12:
        return 0.0, p2.mean(0)
    cx = ((x + x1) * cr).sum() / (6 * a)
    cy = ((y + y1) * cr).sum() / (6 * a)
    return a, np.array([cx, cy])


def section_loops(mesh, origin, normal):
    """Closed loops of the plane section as (pts3d, signed-area-sorted info)."""
    try:
        sec = mesh.section(plane_origin=origin, plane_normal=normal)
    except Exception:
        return []
    if sec is None:
        return []
    n, u, v = _frame(normal)
    out = []
    for d in sec.discrete:
        d = np.asarray(d)
        if len(d) < 4 or np.linalg.norm(d[0] - d[-1]) > 1e-4:
            continue
        p = d[:-1]
        p2 = np.stack([(p - origin) @ u, (p - origin) @ v], 1)
        a, c2 = _poly_area_centroid(p2)
        if abs(a) < 1e-6:
            continue
        c3 = origin + c2[0] * u + c2[1] * v
        out.append({'pts': p, 'area': abs(a), 'centroid': c3})
    return out


def _nearest(loops, target, max_dist):
    best, bd = None, max_dist
    for lp in loops:
        d = np.linalg.norm(lp['centroid'] - target)
        if d < bd:
            best, bd = lp, d
    return best


def _outer_only(loops):
    """Drop loops that lie inside another loop's bounding circle (holes)."""
    keep = []
    for i, a in enumerate(loops):
        inside = False
        for j, b in enumerate(loops):
            if i != j and b['area'] > a['area']:
                r = np.sqrt(b['area'] / np.pi) * 1.5
                if np.linalg.norm(a['centroid'] - b['centroid']) < r:
                    inside = True
                    break
        if not inside:
            keep.append(a)
    return keep


def track(mesh, start_loop, normal, bend, bounds_r):
    """March from `start_loop` along +normal. Returns list of sections
    (centroid, tangent, pts, area), including the start."""
    T = np.asarray(normal, float) / np.linalg.norm(normal)
    c = start_loop['centroid']
    secs = [(c, T, start_loop['pts'], start_loop['area'])]
    area = start_loop['area']
    tol = max(3 * STEP, 0.5 * np.sqrt(area))
    for _ in range(MAX_STEPS):
        p = c + STEP * T
        if np.linalg.norm(p) > bounds_r:
            break
        lp = _nearest(_outer_only(section_loops(mesh, p, T)), p, tol)
        if lp is None:
            break
        Tn = T
        if bend:
            d = lp['centroid'] - c
            if np.linalg.norm(d) > 1e-6:
                Tn = d / np.linalg.norm(d)
                Tn = Tn / np.linalg.norm(Tn)
                p2 = c + STEP * Tn
                lp2 = _nearest(_outer_only(section_loops(mesh, p2, Tn)), p2, tol)
                if lp2 is not None:
                    lp = lp2
        r = lp['area'] / area
        if not (AREA_JUMP[0] <= r <= AREA_JUMP[1]):
            break
        c, T, area = lp['centroid'], Tn, lp['area']
        secs.append((c, T, lp['pts'], area))
    return secs


def refine_end(mesh, c, T, area, max_ext=STEP):
    """Largest t in [0, max_ext] such that a matching section still exists at c + t*T."""
    lo, hi = 0.0, max_ext
    tol = max(3 * STEP, 0.5 * np.sqrt(area))
    for _ in range(6):
        mid = 0.5 * (lo + hi)
        p = c + mid * T
        if _nearest(_outer_only(section_loops(mesh, p, T)), p, tol) is not None:
            lo = mid
        else:
            hi = mid
    return lo


def resample(pts, n, T, ref):
    """Resample a closed loop to n points by arc length, CCW about T, starting
    at the point furthest along `ref` (projected into the section plane)."""
    p = np.asarray(pts, float)
    c = p.mean(0)
    _, u, v = _frame(T)
    p2 = np.stack([(p - c) @ u, (p - c) @ v], 1)
    if _poly_area_centroid(p2)[0] < 0:
        p = p[::-1]
    seg = np.linalg.norm(np.roll(p, -1, 0) - p, axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    L = s[-1]
    if L <= 0:
        return None
    q = np.linspace(0, L, n, endpoint=False)
    pc = np.vstack([p, p[:1]])
    out = np.stack([np.interp(q, s, pc[:, k]) for k in range(3)], 1)
    r = ref - (ref @ T) * T
    if np.linalg.norm(r) > 1e-9:
        k = int(np.argmax((out - out.mean(0)) @ r))
        out = np.roll(out, -k, 0)
    return out


def align_to(prev, cur):
    """Cyclic shift of `cur` minimizing distance to `prev` (both centered)."""
    a = prev - prev.mean(0)
    b = cur - cur.mean(0)
    best, bk = None, 0
    for k in range(len(b)):
        d = np.sum((np.roll(b, -k, 0) - a) ** 2)
        if best is None or d < best:
            best, bk = d, k
    return np.roll(cur, -bk, 0)


def keyframes(rs, tol):
    """Indices of sections such that linear interpolation between kept ones
    reproduces every dropped section within `tol` (max point distance)."""
    keep = {0, len(rs) - 1}

    def rec(i, j):
        if j - i < 2:
            return
        worst, wk = 0.0, None
        for k in range(i + 1, j):
            t = (k - i) / (j - i)
            err = np.max(np.linalg.norm((1 - t) * rs[i] + t * rs[j] - rs[k], axis=1))
            if err > worst:
                worst, wk = err, k
        if worst > tol:
            keep.add(wk)
            rec(i, wk)
            rec(wk, j)

    rec(0, len(rs) - 1)
    return sorted(keep)


def smooth_path(path, window=5, n_out=8):
    """Moving-average the centroid path (endpoints pinned), then resample it
    evenly by arc length. Raw section centroids zigzag near the caps and a
    spline through them makes the swept tube self-intersect."""
    P = np.asarray(path, float)
    if len(P) > window:
        k = window // 2
        Q = P.copy()
        for i in range(1, len(P) - 1):
            lo, hi = max(0, i - k), min(len(P), i + k + 1)
            Q[i] = P[lo:hi].mean(0)
        P = Q
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    if s[-1] <= 0:
        return P
    q = np.linspace(0, s[-1], min(n_out, len(P)))
    return np.stack([np.interp(q, s, P[:, j]) for j in range(3)], 1)


# ---------------------------------------------------------------- code

def _fmt(pts):
    return '[' + ', '.join(f'({x:.5f}, {y:.5f}, {z:.5f})' for x, y, z in pts) + ']'


def loft_code(sections):
    lines = [f'g{{N}}_secs = [']
    lines += [f'    {_fmt(s)},' for s in sections]
    lines += [']',
              'g{N}_wires = [cq.Wire.assembleEdges([cq.Edge.makeSpline([cq.Vector(*p) for p in s], periodic=True)]) for s in g{N}_secs]',
              'g{N}_solid = cq.Solid.makeLoft(g{N}_wires, ruled=False)',
              'assert g{N}_solid.isValid(), "invalid loft"',
              'solid_gen_{N} = cq.Workplane("XY").add(g{N}_solid)']
    return '\n'.join(lines)


def sweep_code(section_pts, section_normal, path, frenet):
    """Sweep a section (taken anywhere along the path) along `path`.

    The section is expressed in its own plane frame, then placed at the path
    start with the frame carried over (x axis projected onto the start plane).
    It is emitted in plane coordinates and mapped with the exact plane:
    rounded 3D points are off-plane by ~1e-6 and OCC then returns an open
    shell instead of a solid."""
    P = np.asarray(section_pts, float)
    ns = np.asarray(section_normal, float)
    ns = ns / np.linalg.norm(ns)
    _, us, vs = _frame(ns)
    p2d = np.stack([(P - P.mean(0)) @ us, (P - P.mean(0)) @ vs], 1)
    a, c2 = _poly_area_centroid(p2d)
    p2d = p2d - c2
    if a < 0:
        p2d = p2d[::-1]
    path = np.asarray(path, float)
    n = path[1] - path[0]
    n = n / np.linalg.norm(n)
    u = us - (us @ n) * n
    if np.linalg.norm(u) < 1e-6:
        u = _frame(n)[1]
    u = u / np.linalg.norm(u)
    c = path[0]
    pts2 = '[' + ', '.join(f'({x:.5f}, {y:.5f})' for x, y in p2d) + ']'
    return '\n'.join([
        f'g{{N}}_pl = cq.Plane(origin=({c[0]:.6f}, {c[1]:.6f}, {c[2]:.6f}), xDir=({u[0]:.7f}, {u[1]:.7f}, {u[2]:.7f}), '
        f'normal=({n[0]:.7f}, {n[1]:.7f}, {n[2]:.7f}))',
        f'g{{N}}_prof = {pts2}',
        f'g{{N}}_path = {_fmt(path)}',
        'g{N}_pw = cq.Wire.assembleEdges([cq.Edge.makeSpline([g{N}_pl.toWorldCoords(p) for p in g{N}_prof], periodic=True)])',
        'g{N}_sw = cq.Wire.assembleEdges([cq.Edge.makeSpline([cq.Vector(*p) for p in g{N}_path])])',
        f'g{{N}}_solid = cq.Solid.sweep(g{{N}}_pw, [], g{{N}}_sw, makeSolid=True, isFrenet={frenet})',
        'assert g{N}_solid.isValid(), "invalid sweep"',
        'solid_gen_{N} = cq.Workplane("XY").add(g{N}_solid)',
    ])


# ---------------------------------------------------------------- driver

def full_track(mesh, seed, normal, bend, bounds_r):
    """Track both ways from a seed loop and return sections ordered end to end."""
    fwd = track(mesh, seed, normal, bend, bounds_r)
    bwd = track(mesh, seed, -np.asarray(normal, float), bend, bounds_r)
    secs = [(c, -T, p, a) for c, T, p, a in bwd[::-1]] + fwd[1:]
    if len(secs) < 3:
        return None
    # Push both ends out to where the section vanishes.
    c0, T0, _, a0 = secs[0]
    t0 = refine_end(mesh, c0, -T0, a0)
    c1, T1, _, a1 = secs[-1]
    t1 = refine_end(mesh, c1, T1, a1)
    # Stay a hair inside the cap: a section exactly on a cap face degenerates.
    t0, t1 = max(t0 - 0.004, 0.0), max(t1 - 0.004, 0.0)
    lf = _nearest(_outer_only(section_loops(mesh, c0 - t0 * T0, T0)), c0 - t0 * T0, 3 * STEP)
    ll = _nearest(_outer_only(section_loops(mesh, c1 + t1 * T1, T1)), c1 + t1 * T1, 3 * STEP)
    if lf is not None and AREA_JUMP[0] <= lf['area'] / a0 <= AREA_JUMP[1]:
        secs.insert(0, (lf['centroid'], T0, lf['pts'], lf['area']))
    if ll is not None and AREA_JUMP[0] <= ll['area'] / a1 <= AREA_JUMP[1]:
        secs.append((ll['centroid'], T1, ll['pts'], ll['area']))
    return secs


def _track_key(secs):
    a, b = secs[0][0], secs[-1][0]
    if tuple(np.round(a, 2)) > tuple(np.round(b, 2)):
        a, b = b, a
    return np.concatenate([a, b])


def resampled(secs):
    ref = _frame(secs[0][1])[1]
    rs = []
    for c, T, p, _ in secs:
        r = resample(p, M_PTS, T, ref)
        if r is None:
            return None
        if rs:
            r = align_to(rs[-1], r)
        rs.append(r)
        ref = r[0] - r.mean(0)
    return rs


def _novel(secs, tracks, tol=0.03):
    k = _track_key(secs)
    if any(np.linalg.norm(k - t) < tol for t in tracks):
        return False
    tracks.append(k)
    return True


def propose(mesh, entries, bounds_r):
    cands = []
    seen = []
    tracks = []
    for idx, e in enumerate(entries):
        loops = e.get('loops_3d') or []
        if len(loops) != 1:
            continue
        p = np.asarray(loops[0], float)
        normal = np.asarray(e['normal'], float)
        origin = np.asarray(e['origin'], float)
        # Re-section at the seed plane so the seed matches the tracker's loops.
        lp = _nearest(_outer_only(section_loops(mesh, origin, normal)), p.mean(0), 0.2)
        if lp is None:
            continue
        key = np.concatenate([lp['centroid'], np.abs(normal), [lp['area']]])
        if any(np.linalg.norm(key - k) < 0.02 for k in seen):
            continue
        seen.append(key)
        if len(seen) > MAX_SEEDS:
            break
        size = np.sqrt(lp['area'])

        # Straight track -> loft if the section changes.
        secs = full_track(mesh, lp, normal, False, bounds_r)
        if secs and _novel(secs, tracks):
            rs = resampled(secs)
            if rs:
                c = [r - r.mean(0) for r in rs]
                var = max(np.max(np.linalg.norm(ci - c[0], axis=1)) for ci in c) / max(size, 1e-6)
                drift = np.linalg.norm(np.cross(rs[-1].mean(0) - rs[0].mean(0), normal)) / max(size, 1e-6)
                if var > MIN_REL_VAR or drift > MIN_REL_VAR:
                    kf = keyframes(rs, tol=0.01)
                    cands.append({'kind': 'loft', 'seed_idx': idx, 'n_sections': len(kf),
                                  'length': float(np.linalg.norm(rs[-1].mean(0) - rs[0].mean(0))),
                                  'code': loft_code([rs[k] for k in kf])})

        # Bent track -> sweep (+ loft through the tilted sections).
        secs = full_track(mesh, lp, normal, True, bounds_r)
        if secs and _novel(secs, tracks):
            Ts = np.array([s[1] for s in secs])
            turn = np.degrees(np.arccos(np.clip(Ts[0] @ Ts[-1], -1, 1)))
            if turn > MIN_TURN_DEG:
                rs = resampled(secs)
                if rs:
                    path = smooth_path(np.array([r.mean(0) for r in rs]))
                    # Profile from a representative interior section (median
                    # area): sections at the ends graze the caps and are clipped.
                    areas = np.array([sec[3] for sec in secs])
                    k = int(np.argmin(np.abs(areas - np.median(areas))))
                    for fr in (True, False):
                        cands.append({'kind': 'sweep', 'seed_idx': idx, 'turn_deg': float(turn), 'frenet': fr,
                                      'code': sweep_code(secs[k][2], secs[k][1], path, fr)})
                    kf = keyframes(rs, tol=0.01)
                    cands.append({'kind': 'loft', 'seed_idx': idx, 'n_sections': len(kf), 'bent': True,
                                  'code': loft_code([rs[k] for k in kf])})
    return cands


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('loops_json')
    ap.add_argument('mesh')
    ap.add_argument('--out', default='sweep_loft_candidates.json')
    ap.add_argument('--normalize', action='store_true')
    args = ap.parse_args()
    mesh = trimesh.load(args.mesh, force='mesh')
    if args.normalize:
        mesh = normalize_mesh(mesh)
    entries = json.load(open(args.loops_json))
    bounds_r = float(np.linalg.norm(mesh.bounds, axis=1).max()) + 0.1
    with np.errstate(all='ignore'):
        cands = propose(mesh, entries, bounds_r)
    json.dump(cands, open(args.out, 'w'), indent=1)
    kinds = {}
    for c in cands:
        kinds[c['kind']] = kinds.get(c['kind'], 0) + 1
    print(f'wrote {len(cands)} candidates {kinds} to {args.out}', file=sys.stderr)


if __name__ == '__main__':
    main()

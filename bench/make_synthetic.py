#!/usr/bin/env python3
"""
Generate a small synthetic benchmark of CAD parts with known construction.

Each part is built with CadQuery from one of a handful of parametric families
(extrudes, cuts, revolves, multi-body, rotated frames), exported to STL, and
recorded in manifest.json with its family, parameters and number of
ground-truth operations.

Usage:
  python bench/make_synthetic.py --out bench/synthetic --per-family 3 --seed 0
"""
import argparse
import json
import math
import os
import random

import cadquery as cq


def plate_with_holes(r):
    L, W, T = r.uniform(40, 90), r.uniform(30, 60), r.uniform(3, 10)
    d = r.uniform(3, 7)
    nx = r.choice([2, 3])
    wp = cq.Workplane("XY").box(L, W, T)
    pts = [(-L / 2 + L * (i + 1) / (nx + 1), s * W / 4) for i in range(nx) for s in (-1, 1)]
    wp = wp.faces(">Z").workplane().pushPoints(pts).hole(d)
    return wp, dict(L=L, W=W, T=T, d=d, n_holes=len(pts)), 2


def l_bracket(r):
    a, b, t, depth = r.uniform(30, 60), r.uniform(20, 50), r.uniform(4, 10), r.uniform(15, 40)
    pts = [(0, 0), (a, 0), (a, t), (t, t), (t, b), (0, b)]
    wp = cq.Workplane("XZ").polyline(pts).close().extrude(depth)
    return wp, dict(a=a, b=b, t=t, depth=depth), 1


def stepped_block(r):
    L, W, h1 = r.uniform(40, 80), r.uniform(30, 60), r.uniform(8, 20)
    s, h2 = r.uniform(0.4, 0.7), r.uniform(8, 25)
    wp = cq.Workplane("XY").box(L, W, h1, centered=(True, True, False))
    wp = wp.faces(">Z").workplane().rect(L * s, W * s).extrude(h2)
    return wp, dict(L=L, W=W, h1=h1, s=s, h2=h2), 2


def boss_on_plate(r):
    L, T, rb, hb = r.uniform(40, 80), r.uniform(4, 10), r.uniform(6, 14), r.uniform(10, 30)
    bore = rb * r.uniform(0.3, 0.6)
    wp = cq.Workplane("XY").box(L, L, T, centered=(True, True, False))
    wp = wp.faces(">Z").workplane().circle(rb).extrude(hb)
    wp = wp.faces(">Z").workplane().hole(2 * bore)
    return wp, dict(L=L, T=T, rb=rb, hb=hb, bore=bore), 3


def box_with_pocket(r):
    L, W, H = r.uniform(40, 80), r.uniform(30, 60), r.uniform(15, 30)
    s, dp = r.uniform(0.5, 0.75), r.uniform(0.3, 0.7)
    wp = cq.Workplane("XY").box(L, W, H, centered=(True, True, False))
    wp = wp.faces(">Z").workplane().rect(L * s, W * s).cutBlind(-H * dp)
    return wp, dict(L=L, W=W, H=H, s=s, dp=dp), 2


def u_channel(r):
    w, h, t, depth = r.uniform(25, 50), r.uniform(20, 40), r.uniform(3, 7), r.uniform(40, 90)
    pts = [(0, 0), (w, 0), (w, h), (w - t, h), (w - t, t), (t, t), (t, h), (0, h)]
    wp = cq.Workplane("XY").polyline(pts).close().extrude(depth)
    return wp, dict(w=w, h=h, t=t, depth=depth), 1


def hex_prism(r):
    d, h = r.uniform(20, 45), r.uniform(10, 40)
    bore = d * r.uniform(0.25, 0.5)
    wp = cq.Workplane("XY").polygon(6, d).extrude(h).faces(">Z").workplane().hole(bore)
    return wp, dict(d=d, h=h, bore=bore), 2


def stepped_shaft(r):
    r1, r2, r3 = r.uniform(12, 20), r.uniform(7, 11), r.uniform(3, 6)
    l1, l2, l3 = r.uniform(10, 25), r.uniform(15, 35), r.uniform(10, 25)
    pts = [(0, 0), (r1, 0), (r1, l1), (r2, l1), (r2, l1 + l2), (r3, l1 + l2),
           (r3, l1 + l2 + l3), (0, l1 + l2 + l3)]
    wp = cq.Workplane("XZ").polyline(pts).close().revolve(360, (0, 0, 0), (0, 1, 0))
    return wp, dict(r1=r1, r2=r2, r3=r3, l1=l1, l2=l2, l3=l3), 1


def flange(r):
    ro, ri, t = r.uniform(30, 50), r.uniform(6, 12), r.uniform(5, 10)
    rh, hh = r.uniform(14, 22), r.uniform(15, 30)
    pts = [(ri, 0), (ro, 0), (ro, t), (rh, t), (rh, t + hh), (ri, t + hh)]
    wp = cq.Workplane("XZ").polyline(pts).close().revolve(360, (0, 0, 0), (0, 1, 0))
    n = r.choice([4, 6])
    wp = wp.faces("<Z").workplane().polarArray((ro + rh) / 2, 0, 360, n).hole(r.uniform(3, 5))
    return wp, dict(ro=ro, ri=ri, t=t, rh=rh, hh=hh, n_bolt=n), 2


def pulley(r):
    ro, ri, w = r.uniform(20, 40), r.uniform(4, 9), r.uniform(10, 20)
    g = r.uniform(0.15, 0.3) * ro
    pts = [(ri, 0), (ro, 0), (ro, w * 0.25), (ro - g, w * 0.5), (ro, w * 0.75), (ro, w), (ri, w)]
    wp = cq.Workplane("XZ").polyline(pts).close().revolve(360, (0, 0, 0), (0, 1, 0))
    return wp, dict(ro=ro, ri=ri, w=w, g=g), 1


FAMILIES = [plate_with_holes, l_bracket, stepped_block, boss_on_plate, box_with_pocket,
            u_channel, hex_prism, stepped_shaft, flange, pulley]


# ---- Phase 3 families: operations stock CADFit cannot express --------------

def loft_square_circle(r):
    a, rc, h = r.uniform(20, 40), r.uniform(6, 14), r.uniform(20, 50)
    wp = cq.Workplane("XY").rect(a, a).workplane(offset=h).circle(rc).loft(ruled=False)
    return wp, dict(op="loft", a=a, rc=rc, h=h, axis=[0, 0, 1]), 1


def tapered_boss(r):
    r0, r1, h = r.uniform(12, 20), r.uniform(4, 10), r.uniform(15, 40)
    L, T = r.uniform(50, 80), r.uniform(4, 8)
    base = cq.Workplane("XY").box(L, L, T, centered=(True, True, False))
    cone = cq.Workplane("XY").workplane(offset=T).circle(r0).workplane(offset=h).circle(r1).loft()
    return base.union(cone), dict(op="loft", r0=r0, r1=r1, h=h, L=L, T=T, axis=[0, 0, 1]), 2


def bent_pipe(r):
    R, rp, ang = r.uniform(25, 45), r.uniform(4, 9), r.uniform(60, 150)
    th = math.radians(ang)
    # Arc centred at (R, 0) in the XZ plane, starting at the origin tangent to +Z.
    mid = (R - R * math.cos(th / 2), R * math.sin(th / 2))
    end = (R - R * math.cos(th), R * math.sin(th))
    path = cq.Workplane("XZ").threePointArc(mid, end)
    wp = cq.Workplane("XY").circle(rp).sweep(path)
    return wp, dict(op="sweep", R=R, rp=rp, angle=ang), 1


def s_swept_bar(r):
    w, t, L, amp = r.uniform(6, 12), r.uniform(3, 6), r.uniform(50, 90), r.uniform(8, 20)
    pts = [(0, 0), (amp, L * 0.33), (-amp, L * 0.66), (0, L)]
    path = cq.Workplane("XZ").spline(pts)
    wp = cq.Workplane("XY").rect(w, t).sweep(path)
    return wp, dict(op="sweep", w=w, t=t, L=L, amp=amp), 1


def plate_with_loft_handle(r):
    L, W, T = r.uniform(60, 90), r.uniform(30, 50), r.uniform(4, 8)
    a, rc, h = r.uniform(10, 18), r.uniform(3, 6), r.uniform(15, 30)
    base = cq.Workplane("XY").box(L, W, T, centered=(True, True, False))
    handle = cq.Workplane("XY").workplane(offset=T).rect(a, a).workplane(offset=h).circle(rc).loft()
    return base.union(handle), dict(op="loft", L=L, W=W, T=T, a=a, rc=rc, h=h, axis=[0, 0, 1]), 2


FAMILIES_P3 = [loft_square_circle, tapered_boss, bent_pipe, s_swept_bar, plate_with_loft_handle]


def main():
    ap = argparse.ArgumentParser(description="Generate synthetic CAD benchmark STLs")
    ap.add_argument("--out", default="bench/synthetic")
    ap.add_argument("--per-family", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--p3", action="store_true", help="phase-3 families (loft/sweep) instead of the originals")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    r = random.Random(args.seed)
    manifest = []
    for fam in (FAMILIES_P3 if args.p3 else FAMILIES):
        for k in range(args.per_family):
            wp, params, n_ops = fam(r)
            # Last variant of each family is tilted so its planes are off-axis.
            rotated = k == args.per_family - 1
            if rotated:
                ang = r.uniform(15, 40)
                wp = wp.rotate((0, 0, 0), (1, 1, 0), ang)
                params["tilt_deg"] = ang
            name = f"{fam.__name__}_{k}"
            path = os.path.join(args.out, f"{name}.stl")
            cq.exporters.export(wp, path, tolerance=0.01, angularTolerance=0.1)
            manifest.append(dict(name=name, family=fam.__name__, rotated=rotated,
                                 gt_ops=n_ops, params=params))
            print(f"  {name}: gt_ops={n_ops} rotated={rotated}")

    with open(os.path.join(args.out, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Wrote {len(manifest)} parts to {args.out}")


if __name__ == "__main__":
    main()

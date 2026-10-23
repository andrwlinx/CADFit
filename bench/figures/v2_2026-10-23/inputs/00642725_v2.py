import cadquery as cq

def _shape(w):
    if isinstance(w, cq.Workplane):
        vs = [v for v in w.vals() if isinstance(v, cq.Shape)]
        return vs[0] if len(vs) == 1 else cq.Compound.makeCompound(vs)
    return w


def _good(s):
    try:
        return s is not None and s.isValid() and s.Volume() > 1e-9
    except Exception:
        return False


def _fuse(a, b):
    """Boolean union; fuzzy retries; if all fail, keep both bodies as a compound."""
    A, B = _shape(a), _shape(b)
    for tol in (None, 1e-5, 1e-4):
        try:
            r = A.fuse(B, tol=tol).clean()
            if _good(r):
                return cq.Workplane("XY").newObject([r])
        except Exception:
            pass
    return cq.Workplane("XY").newObject([cq.Compound.makeCompound([A, B])])


def _cut(a, b):
    """Boolean difference; fuzzy retries; if all fail, the cut is skipped."""
    A, B = _shape(a), _shape(b)
    for tol in (None, 1e-5, 1e-4):
        try:
            r = A.cut(B, tol=tol).clean()
            if _good(r):
                return cq.Workplane("XY").newObject([r])
        except Exception:
            pass
    return cq.Workplane("XY").newObject([A])

import math

# Section_z operation 1
g1_solids = []
g1_outer = cq.Wire.makePolygon([cq.Vector(*q) for q in [(-0.79692, -0.51192, -0.20478), (-0.77028, -0.50723, -0.20478), (-0.74756, -0.49255, -0.20478), (-0.73232, -0.47020, -0.20478), (-0.72696, -0.44369, -0.20478), (-0.73232, -0.41717, -0.20478), (-0.74756, -0.39482, -0.20478), (-0.76715, -0.38147, -0.20478), (-0.79352, -0.37545, -0.20478), (-0.82016, -0.38015, -0.20478), (-0.84288, -0.39482, -0.20478), (-0.85812, -0.41717, -0.20478), (-0.86348, -0.44369, -0.20478), (-0.85812, -0.47020, -0.20478), (-0.84288, -0.49255, -0.20478), (-0.82330, -0.50590, -0.20478)]], close=True)
g1_holes = []
g1_solids.append(cq.Solid.extrudeLinear(cq.Face.makeFromWires(g1_outer, g1_holes), cq.Vector(0.00000, 0.00000, 0.40956)))
g1_outer = cq.Wire.makePolygon([cq.Vector(*q) for q in [(-0.55119, -0.51192, -0.20478), (-0.52455, -0.50723, -0.20478), (-0.50183, -0.49255, -0.20478), (-0.48659, -0.47020, -0.20478), (-0.48123, -0.44369, -0.20478), (-0.48659, -0.41717, -0.20478), (-0.50183, -0.39482, -0.20478), (-0.52141, -0.38147, -0.20478), (-0.54779, -0.37545, -0.20478), (-0.57443, -0.38015, -0.20478), (-0.59715, -0.39482, -0.20478), (-0.61099, -0.41407, -0.20478), (-0.61766, -0.44028, -0.20478), (-0.61363, -0.46703, -0.20478), (-0.59953, -0.49011, -0.20478), (-0.57756, -0.50590, -0.20478)]], close=True)
g1_holes = []
g1_solids.append(cq.Solid.extrudeLinear(cq.Face.makeFromWires(g1_outer, g1_holes), cq.Vector(0.00000, 0.00000, 0.40956)))
g1_outer = cq.Wire.makePolygon([cq.Vector(*q) for q in [(0.54779, -0.51192, -0.20478), (0.57443, -0.50723, -0.20478), (0.59715, -0.49255, -0.20478), (0.61239, -0.47020, -0.20478), (0.61775, -0.44369, -0.20478), (0.61363, -0.42034, -0.20478), (0.59953, -0.39726, -0.20478), (0.57756, -0.38147, -0.20478), (0.55119, -0.37545, -0.20478), (0.52455, -0.38015, -0.20478), (0.50183, -0.39482, -0.20478), (0.48659, -0.41717, -0.20478), (0.48131, -0.44028, -0.20478), (0.48535, -0.46703, -0.20478), (0.49945, -0.49011, -0.20478), (0.52141, -0.50590, -0.20478)]], close=True)
g1_holes = []
g1_solids.append(cq.Solid.extrudeLinear(cq.Face.makeFromWires(g1_outer, g1_holes), cq.Vector(0.00000, 0.00000, 0.40956)))
g1_outer = cq.Wire.makePolygon([cq.Vector(*q) for q in [(0.79352, -0.51192, -0.20478), (0.82016, -0.50723, -0.20478), (0.84288, -0.49255, -0.20478), (0.85812, -0.47020, -0.20478), (0.86348, -0.44369, -0.20478), (0.85936, -0.42034, -0.20478), (0.84526, -0.39726, -0.20478), (0.82330, -0.38147, -0.20478), (0.79692, -0.37545, -0.20478), (0.77028, -0.38015, -0.20478), (0.74756, -0.39482, -0.20478), (0.73232, -0.41717, -0.20478), (0.72705, -0.44028, -0.20478), (0.73108, -0.46703, -0.20478), (0.74518, -0.49011, -0.20478), (0.76715, -0.50590, -0.20478)]], close=True)
g1_holes = []
g1_solids.append(cq.Solid.extrudeLinear(cq.Face.makeFromWires(g1_outer, g1_holes), cq.Vector(0.00000, 0.00000, 0.40956)))
g1_outer = cq.Wire.makePolygon([cq.Vector(*q) for q in [(-0.79692, -0.26619, -0.20478), (-0.77028, -0.26149, -0.20478), (-0.74756, -0.24682, -0.20478), (-0.73232, -0.22447, -0.20478), (-0.72696, -0.19795, -0.20478), (-0.73232, -0.17144, -0.20478), (-0.74756, -0.14909, -0.20478), (-0.77028, -0.13441, -0.20478), (-0.79352, -0.12971, -0.20478), (-0.82016, -0.13441, -0.20478), (-0.84288, -0.14909, -0.20478), (-0.85812, -0.17144, -0.20478), (-0.86348, -0.19795, -0.20478), (-0.85812, -0.22447, -0.20478), (-0.84288, -0.24682, -0.20478), (-0.82330, -0.26017, -0.20478)]], close=True)
g1_holes = []
g1_solids.append(cq.Solid.extrudeLinear(cq.Face.makeFromWires(g1_outer, g1_holes), cq.Vector(0.00000, 0.00000, 0.40956)))
g1_outer = cq.Wire.makePolygon([cq.Vector(*q) for q in [(-0.55119, -0.26619, -0.20478), (-0.52455, -0.26149, -0.20478), (-0.50183, -0.24682, -0.20478), (-0.48659, -0.22447, -0.20478), (-0.48123, -0.19795, -0.20478), (-0.48659, -0.17144, -0.20478), (-0.50183, -0.14909, -0.20478), (-0.52455, -0.13441, -0.20478), (-0.54779, -0.12971, -0.20478), (-0.57443, -0.13441, -0.20478), (-0.59465, -0.14677, -0.20478), (-0.61099, -0.16834, -0.20478), (-0.61766, -0.19455, -0.20478), (-0.61363, -0.22130, -0.20478), (-0.59953, -0.24438, -0.20478), (-0.57756, -0.26017, -0.20478)]], close=True)
g1_holes = []
g1_solids.append(cq.Solid.extrudeLinear(cq.Face.makeFromWires(g1_outer, g1_holes), cq.Vector(0.00000, 0.00000, 0.40956)))
g1_outer = cq.Wire.makePolygon([cq.Vector(*q) for q in [(0.54779, -0.26619, -0.20478), (0.57443, -0.26149, -0.20478), (0.59715, -0.24682, -0.20478), (0.61239, -0.22447, -0.20478), (0.61775, -0.19795, -0.20478), (0.61363, -0.17461, -0.20478), (0.59953, -0.15152, -0.20478), (0.57756, -0.13573, -0.20478), (0.55119, -0.12971, -0.20478), (0.52455, -0.13441, -0.20478), (0.50432, -0.14677, -0.20478), (0.48799, -0.16834, -0.20478), (0.48131, -0.19455, -0.20478), (0.48535, -0.22130, -0.20478), (0.49945, -0.24438, -0.20478), (0.52141, -0.26017, -0.20478)]], close=True)
g1_holes = []
g1_solids.append(cq.Solid.extrudeLinear(cq.Face.makeFromWires(g1_outer, g1_holes), cq.Vector(0.00000, 0.00000, 0.40956)))
g1_outer = cq.Wire.makePolygon([cq.Vector(*q) for q in [(0.79352, -0.26619, -0.20478), (0.82016, -0.26149, -0.20478), (0.84288, -0.24682, -0.20478), (0.85812, -0.22447, -0.20478), (0.86348, -0.19795, -0.20478), (0.85936, -0.17461, -0.20478), (0.84526, -0.15152, -0.20478), (0.82330, -0.13573, -0.20478), (0.79692, -0.12971, -0.20478), (0.77028, -0.13441, -0.20478), (0.75006, -0.14677, -0.20478), (0.73372, -0.16834, -0.20478), (0.72705, -0.19455, -0.20478), (0.73108, -0.22130, -0.20478), (0.74518, -0.24438, -0.20478), (0.76715, -0.26017, -0.20478)]], close=True)
g1_holes = []
g1_solids.append(cq.Solid.extrudeLinear(cq.Face.makeFromWires(g1_outer, g1_holes), cq.Vector(0.00000, 0.00000, 0.40956)))
g1_outer = cq.Wire.makePolygon([cq.Vector(*q) for q in [(-0.79692, -0.02046, -0.20478), (-0.77028, -0.01576, -0.20478), (-0.74756, -0.00108, -0.20478), (-0.73232, 0.02127, -0.20478), (-0.72696, 0.04778, -0.20478), (-0.73232, 0.07430, -0.20478), (-0.74756, 0.09665, -0.20478), (-0.77028, 0.11132, -0.20478), (-0.79352, 0.11602, -0.20478), (-0.82016, 0.11132, -0.20478), (-0.84288, 0.09665, -0.20478), (-0.85812, 0.07430, -0.20478), (-0.86348, 0.04778, -0.20478), (-0.85812, 0.02127, -0.20478), (-0.84288, -0.00108, -0.20478), (-0.82330, -0.01444, -0.20478)]], close=True)
g1_holes = []
g1_solids.append(cq.Solid.extrudeLinear(cq.Face.makeFromWires(g1_outer, g1_holes), cq.Vector(0.00000, 0.00000, 0.40956)))
g1_outer = cq.Wire.makePolygon([cq.Vector(*q) for q in [(-0.55119, -0.02046, -0.20478), (-0.52455, -0.01576, -0.20478), (-0.50183, -0.00108, -0.20478), (-0.48659, 0.02127, -0.20478), (-0.48123, 0.04778, -0.20478), (-0.48659, 0.07430, -0.20478), (-0.50183, 0.09665, -0.20478), (-0.52455, 0.11132, -0.20478), (-0.54779, 0.11602, -0.20478), (-0.57443, 0.11132, -0.20478), (-0.59465, 0.09896, -0.20478), (-0.61099, 0.07740, -0.20478), (-0.61766, 0.05118, -0.20478), (-0.61363, 0.02444, -0.20478), (-0.59953, 0.00135, -0.20478), (-0.57756, -0.01444, -0.20478)]], close=True)
g1_holes = []
g1_solids.append(cq.Solid.extrudeLinear(cq.Face.makeFromWires(g1_outer, g1_holes), cq.Vector(0.00000, 0.00000, 0.40956)))
g1_outer = cq.Wire.makePolygon([cq.Vector(*q) for q in [(0.54779, -0.02046, -0.20478), (0.57443, -0.01576, -0.20478), (0.59715, -0.00108, -0.20478), (0.61239, 0.02127, -0.20478), (0.61775, 0.04778, -0.20478), (0.61363, 0.07113, -0.20478), (0.59953, 0.09421, -0.20478), (0.57756, 0.11000, -0.20478), (0.55119, 0.11602, -0.20478), (0.52455, 0.11132, -0.20478), (0.50432, 0.09896, -0.20478), (0.48799, 0.07740, -0.20478), (0.48131, 0.05118, -0.20478), (0.48535, 0.02444, -0.20478), (0.49945, 0.00135, -0.20478), (0.52141, -0.01444, -0.20478)]], close=True)
g1_holes = []
g1_solids.append(cq.Solid.extrudeLinear(cq.Face.makeFromWires(g1_outer, g1_holes), cq.Vector(0.00000, 0.00000, 0.40956)))
g1_outer = cq.Wire.makePolygon([cq.Vector(*q) for q in [(0.79352, -0.02046, -0.20478), (0.82016, -0.01576, -0.20478), (0.84288, -0.00108, -0.20478), (0.85812, 0.02127, -0.20478), (0.86348, 0.04778, -0.20478), (0.85936, 0.07113, -0.20478), (0.84526, 0.09421, -0.20478), (0.82330, 0.11000, -0.20478), (0.79692, 0.11602, -0.20478), (0.77028, 0.11132, -0.20478), (0.75006, 0.09896, -0.20478), (0.73372, 0.07740, -0.20478), (0.72705, 0.05118, -0.20478), (0.73108, 0.02444, -0.20478), (0.74518, 0.00135, -0.20478), (0.76715, -0.01444, -0.20478)]], close=True)
g1_holes = []
g1_solids.append(cq.Solid.extrudeLinear(cq.Face.makeFromWires(g1_outer, g1_holes), cq.Vector(0.00000, 0.00000, 0.40956)))
g1_outer = cq.Wire.makePolygon([cq.Vector(*q) for q in [(-0.41843, 0.51195, -0.20478), (0.41843, 0.51195, -0.20478), (0.41813, 0.62517, -0.20478), (0.40946, 0.64139, -0.20478), (0.39247, 0.64843, -0.20478), (-0.39513, 0.64817, -0.20478), (-0.41043, 0.64047, -0.20478), (-0.41813, 0.62517, -0.20478)]], close=True)
g1_holes = []
g1_solids.append(cq.Solid.extrudeLinear(cq.Face.makeFromWires(g1_outer, g1_holes), cq.Vector(0.00000, 0.00000, 0.40956)))
g1_shape = g1_solids[0] if len(g1_solids) == 1 else cq.Compound.makeCompound(g1_solids)
assert g1_shape.isValid(), "invalid section extrusion"
solid_gen_1 = cq.Workplane("XY").add(g1_shape)

plane_1 = cq.Plane(origin=(0.0, 0.0, -0.20284), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_1 = cq.Workplane(plane_1)
loop_1 = sketch_1.moveTo(-0.44366, -0.5495)
loop_1 = loop_1.circle(0.06826)
sketch_1=sketch_1.add(loop_1)
solid_1 = sketch_1.extrude(0.38)
plane_2 = cq.Plane(origin=(0.0, 0.0, -0.20284), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_2 = cq.Workplane(plane_2)
loop_1 = sketch_2.moveTo(-0.44366, 0.54942)
loop_1 = loop_1.circle(0.06827)
sketch_2=sketch_2.add(loop_1)
solid_2 = sketch_2.extrude(0.38)
plane_3 = cq.Plane(origin=(-0.99154, 0.5628, -0.0653), normal=(1.0, 1e-05, 0.0), xDir=(1e-05, -1.0, 0.0))
sketch_3 = cq.Workplane(plane_3)
loop_1 = sketch_3.moveTo(1.19422, -0.20291)
loop_1 = loop_1.lineTo(1.2077, -0.21475)
loop_1 = loop_1.threePointArc((1.21049, -0.22181), (1.2112, -0.22969))
loop_1 = loop_1.threePointArc((1.21126, -0.23667), (1.21123, -0.2432))
loop_1 = loop_1.threePointArc((1.20728, -0.25602), (1.19746, -0.26558))
loop_1 = loop_1.lineTo(1.17473, -0.25367)
loop_1 = loop_1.lineTo(1.17202, -0.24104)
loop_1 = loop_1.lineTo(1.17012, -0.22602)
loop_1 = loop_1.lineTo(1.18447, -0.20963)
loop_1 = loop_1.close()
sketch_3=sketch_3.add(loop_1)
solid_3 = sketch_3.extrude(1.98)
plane_4 = cq.Plane(origin=(0.0, -0.63578, 0.0), normal=(0.0, 1.0, 0.0), xDir=(1.0, 0.0, 0.0))
sketch_4 = cq.Workplane(plane_4)
loop_1 = sketch_4.moveTo(0.4872, -0.13536)
loop_1 = loop_1.lineTo(-0.39353, -0.13801)
loop_1 = loop_1.threePointArc((-0.41834, -0.13549), (-0.44096, -0.13602))
loop_1 = loop_1.lineTo(-0.98305, -0.13768)
loop_1 = loop_1.threePointArc((-0.99809, -0.15322), (-0.9987, -0.17314))
loop_1 = loop_1.threePointArc((-0.99823, -0.18591), (-0.99257, -0.19507))
loop_1 = loop_1.threePointArc((-0.97598, -0.20354), (-0.96188, -0.20326))
loop_1 = loop_1.lineTo(0.9853, -0.20077)
loop_1 = loop_1.threePointArc((0.99301, -0.19478), (0.99687, -0.18914))
loop_1 = loop_1.threePointArc((1.00037, -0.16872), (0.99796, -0.15213))
loop_1 = loop_1.threePointArc((0.98113, -0.13705), (0.96368, -0.13642))
loop_1 = loop_1.lineTo(0.48853, -0.13538)
loop_1 = loop_1.close()
sketch_4=sketch_4.add(loop_1)
solid_4 = sketch_4.extrude(1.28)
plane_5 = cq.Plane(origin=(0.99164, 0.57029, -0.06269), normal=(-1.0, -0.0, 0.0), xDir=(-0.0, 1.0, 0.0))
sketch_5 = cq.Workplane(plane_5)
loop_1 = sketch_5.moveTo(-1.02928, -0.19782)
loop_1 = loop_1.lineTo(-1.04161, -0.19834)
loop_1 = loop_1.threePointArc((-1.07226, -0.19866), (-1.09733, -0.19895))
loop_1 = loop_1.lineTo(-1.11017, -0.20991)
loop_1 = loop_1.lineTo(-1.11804, -0.24585)
loop_1 = loop_1.lineTo(-1.10327, -0.26482)
loop_1 = loop_1.lineTo(-1.07114, -0.26487)
loop_1 = loop_1.lineTo(-1.0363, -0.26655)
loop_1 = loop_1.lineTo(-0.74479, -0.26652)
loop_1 = loop_1.lineTo(-0.59843, -0.26645)
loop_1 = loop_1.lineTo(-0.52476, -0.26629)
loop_1 = loop_1.lineTo(-0.50495, -0.25127)
loop_1 = loop_1.lineTo(-0.49447, -0.24535)
loop_1 = loop_1.threePointArc((-0.50142, -0.22541), (-0.50685, -0.21081))
loop_1 = loop_1.lineTo(-0.52072, -0.19936)
loop_1 = loop_1.threePointArc((-0.53001, -0.1983), (-0.53899, -0.19837))
loop_1 = loop_1.lineTo(-0.65083, -0.1982)
loop_1 = loop_1.lineTo(-0.75297, -0.198)
loop_1 = loop_1.lineTo(-0.84386, -0.19844)
loop_1 = loop_1.lineTo(-0.87261, -0.1983)
loop_1 = loop_1.threePointArc((-0.94973, -0.19837), (-1.02854, -0.1982))
loop_1 = loop_1.close()
sketch_5=sketch_5.add(loop_1)
solid_5 = sketch_5.extrude(1.98)

result = solid_gen_1
result = _fuse(result, solid_1)
result = _fuse(result, solid_2)
result = _fuse(result, solid_3)
result = _fuse(result, solid_4)
result = _fuse(result, solid_5)

# Cut operation 1
plane_c1_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c1_1 = cq.Workplane(plane_c1_1)
loop_c1_1 = sketch_c1_1.moveTo(-0.37948, 0.24177)
loop_c1_1 = loop_c1_1.threePointArc((-0.35382, 0.26715), (-0.32935, 0.29168))
loop_c1_1 = loop_c1_1.lineTo(-0.31821, 0.29708)
loop_c1_1 = loop_c1_1.lineTo(-0.25917, 0.23829)
loop_c1_1 = loop_c1_1.lineTo(-0.2615, 0.2233)
loop_c1_1 = loop_c1_1.threePointArc((-0.29183, 0.19302), (-0.32079, 0.16379))
loop_c1_1 = loop_c1_1.lineTo(-0.38364, 0.22699)
loop_c1_1 = loop_c1_1.lineTo(-0.37948, 0.24177)
loop_c1_1 = loop_c1_1.close()
sketch_c1_1=sketch_c1_1.add(loop_c1_1)
solid_c1_1 = sketch_c1_1.extrude(0.04)
cut_1 = solid_c1_1
result = _cut(result, cut_1)

# Cut operation 2
plane_c2_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c2_1 = cq.Workplane(plane_c2_1)
loop_c2_1 = sketch_c2_1.moveTo(-0.08273, 0.07866)
loop_c2_1 = loop_c2_1.threePointArc((-0.07934, 0.09135), (-0.07635, 0.09429))
loop_c2_1 = loop_c2_1.lineTo(-0.02783, 0.14262)
loop_c2_1 = loop_c2_1.threePointArc((-0.01921, 0.1452), (-0.01761, 0.14562))
loop_c2_1 = loop_c2_1.lineTo(0.04121, 0.08785)
loop_c2_1 = loop_c2_1.lineTo(0.04227, 0.07691)
loop_c2_1 = loop_c2_1.lineTo(-0.02074, 0.01393)
loop_c2_1 = loop_c2_1.lineTo(-0.0796, 0.07321)
loop_c2_1 = loop_c2_1.close()
sketch_c2_1=sketch_c2_1.add(loop_c2_1)
solid_c2_1 = sketch_c2_1.extrude(0.04)
cut_2 = solid_c2_1
result = _cut(result, cut_2)

# Cut operation 3
plane_c3_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c3_1 = cq.Workplane(plane_c3_1)
loop_c3_1 = sketch_c3_1.moveTo(-0.08197, -0.06173)
loop_c3_1 = loop_c3_1.threePointArc((-0.05402, -0.03374), (-0.02726, -0.00731))
loop_c3_1 = loop_c3_1.lineTo(-0.01318, -0.00795)
loop_c3_1 = loop_c3_1.threePointArc((0.01512, -0.03606), (0.0405, -0.06127))
loop_c3_1 = loop_c3_1.lineTo(0.03828, -0.07774)
loop_c3_1 = loop_c3_1.lineTo(-0.02074, -0.13623)
loop_c3_1 = loop_c3_1.lineTo(-0.08119, -0.07546)
loop_c3_1 = loop_c3_1.lineTo(-0.08197, -0.06173)
loop_c3_1 = loop_c3_1.close()
sketch_c3_1=sketch_c3_1.add(loop_c3_1)
solid_c3_1 = sketch_c3_1.extrude(0.04)
cut_3 = solid_c3_1
result = _cut(result, cut_3)

# Cut operation 4
plane_c4_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c4_1 = cq.Workplane(plane_c4_1)
loop_c4_1 = sketch_c4_1.moveTo(-0.2306, 0.24015)
loop_c4_1 = loop_c4_1.lineTo(-0.17047, 0.30006)
loop_c4_1 = loop_c4_1.threePointArc((-0.13934, 0.26875), (-0.10943, 0.23889))
loop_c4_1 = loop_c4_1.lineTo(-0.10857, 0.22707)
loop_c4_1 = loop_c4_1.lineTo(-0.13899, 0.19554)
loop_c4_1 = loop_c4_1.lineTo(-0.1641, 0.17063)
loop_c4_1 = loop_c4_1.lineTo(-0.17604, 0.16948)
loop_c4_1 = loop_c4_1.lineTo(-0.20504, 0.19841)
loop_c4_1 = loop_c4_1.lineTo(-0.23209, 0.22595)
loop_c4_1 = loop_c4_1.lineTo(-0.2306, 0.24015)
loop_c4_1 = loop_c4_1.close()
sketch_c4_1=sketch_c4_1.add(loop_c4_1)
solid_c4_1 = sketch_c4_1.extrude(0.04)
cut_4 = solid_c4_1
result = _cut(result, cut_4)

# Cut operation 5
plane_c5_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c5_1 = cq.Workplane(plane_c5_1)
loop_c5_1 = sketch_c5_1.moveTo(-0.5344, -0.06426)
loop_c5_1 = loop_c5_1.lineTo(-0.47071, -0.00037)
loop_c5_1 = loop_c5_1.lineTo(-0.40995, -0.06139)
loop_c5_1 = loop_c5_1.lineTo(-0.40862, -0.07433)
loop_c5_1 = loop_c5_1.lineTo(-0.4624, -0.12706)
loop_c5_1 = loop_c5_1.lineTo(-0.48005, -0.12727)
loop_c5_1 = loop_c5_1.lineTo(-0.53125, -0.07553)
loop_c5_1 = loop_c5_1.lineTo(-0.5344, -0.06426)
loop_c5_1 = loop_c5_1.close()
sketch_c5_1=sketch_c5_1.add(loop_c5_1)
solid_c5_1 = sketch_c5_1.extrude(0.04)
cut_5 = solid_c5_1
result = _cut(result, cut_5)

# Cut operation 6
plane_c6_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c6_1 = cq.Workplane(plane_c6_1)
loop_c6_1 = sketch_c6_1.moveTo(-0.38289, 0.08852)
loop_c6_1 = loop_c6_1.lineTo(-0.34325, 0.12763)
loop_c6_1 = loop_c6_1.lineTo(-0.32769, 0.14037)
loop_c6_1 = loop_c6_1.lineTo(-0.31301, 0.14219)
loop_c6_1 = loop_c6_1.threePointArc((-0.28561, 0.11481), (-0.26121, 0.09035))
loop_c6_1 = loop_c6_1.lineTo(-0.25769, 0.0775)
loop_c6_1 = loop_c6_1.lineTo(-0.32104, 0.01378)
loop_c6_1 = loop_c6_1.lineTo(-0.3475, 0.04036)
loop_c6_1 = loop_c6_1.threePointArc((-0.35613, 0.04923), (-0.36449, 0.0575))
loop_c6_1 = loop_c6_1.lineTo(-0.38134, 0.07461)
loop_c6_1 = loop_c6_1.lineTo(-0.38289, 0.08852)
loop_c6_1 = loop_c6_1.close()
sketch_c6_1=sketch_c6_1.add(loop_c6_1)
solid_c6_1 = sketch_c6_1.extrude(0.04)
cut_6 = solid_c6_1
result = _cut(result, cut_6)

# Cut operation 7
plane_c7_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c7_1 = cq.Workplane(plane_c7_1)
loop_c7_1 = sketch_c7_1.moveTo(-0.23345, 0.08523)
loop_c7_1 = loop_c7_1.lineTo(-0.1704, 0.14981)
loop_c7_1 = loop_c7_1.lineTo(-0.1106, 0.0897)
loop_c7_1 = loop_c7_1.threePointArc((-0.10802, 0.08255), (-0.10723, 0.07884))
loop_c7_1 = loop_c7_1.lineTo(-0.16197, 0.02261)
loop_c7_1 = loop_c7_1.threePointArc((-0.17019, 0.01967), (-0.17509, 0.01923))
loop_c7_1 = loop_c7_1.threePointArc((-0.20547, 0.04866), (-0.23069, 0.0736))
loop_c7_1 = loop_c7_1.threePointArc((-0.23346, 0.0798), (-0.23345, 0.08513))
loop_c7_1 = loop_c7_1.close()
sketch_c7_1=sketch_c7_1.add(loop_c7_1)
solid_c7_1 = sketch_c7_1.extrude(0.04)
cut_7 = solid_c7_1
result = _cut(result, cut_7)

# Cut operation 8
plane_c8_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c8_1 = cq.Workplane(plane_c8_1)
loop_c8_1 = sketch_c8_1.moveTo(-0.53195, 0.23712)
loop_c8_1 = loop_c8_1.threePointArc((-0.5142, 0.25525), (-0.50084, 0.26933))
loop_c8_1 = loop_c8_1.threePointArc((-0.48815, 0.28261), (-0.47621, 0.29543))
loop_c8_1 = loop_c8_1.lineTo(-0.41078, 0.23959)
loop_c8_1 = loop_c8_1.lineTo(-0.41018, 0.22491)
loop_c8_1 = loop_c8_1.lineTo(-0.44622, 0.18851)
loop_c8_1 = loop_c8_1.lineTo(-0.46283, 0.1717)
loop_c8_1 = loop_c8_1.lineTo(-0.47619, 0.1701)
loop_c8_1 = loop_c8_1.threePointArc((-0.50528, 0.19822), (-0.53049, 0.22338))
loop_c8_1 = loop_c8_1.threePointArc((-0.53394, 0.22937), (-0.53609, 0.23375))
loop_c8_1 = loop_c8_1.close()
sketch_c8_1=sketch_c8_1.add(loop_c8_1)
solid_c8_1 = sketch_c8_1.extrude(0.04)
cut_8 = solid_c8_1
result = _cut(result, cut_8)

# Cut operation 9
plane_c9_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c9_1 = cq.Workplane(plane_c9_1)
loop_c9_1 = sketch_c9_1.moveTo(-0.38198, -0.06103)
loop_c9_1 = loop_c9_1.threePointArc((-0.35375, -0.03348), (-0.33204, -0.01184))
loop_c9_1 = loop_c9_1.lineTo(-0.31327, -0.00787)
loop_c9_1 = loop_c9_1.lineTo(-0.26961, -0.05287)
loop_c9_1 = loop_c9_1.lineTo(-0.2594, -0.06327)
loop_c9_1 = loop_c9_1.threePointArc((-0.26086, -0.07539), (-0.26346, -0.0779))
loop_c9_1 = loop_c9_1.threePointArc((-0.29059, -0.10524), (-0.31632, -0.13163))
loop_c9_1 = loop_c9_1.lineTo(-0.34092, -0.11871)
loop_c9_1 = loop_c9_1.lineTo(-0.38214, -0.07395)
loop_c9_1 = loop_c9_1.lineTo(-0.38198, -0.06103)
loop_c9_1 = loop_c9_1.close()
sketch_c9_1=sketch_c9_1.add(loop_c9_1)
solid_c9_1 = sketch_c9_1.extrude(0.04)
cut_9 = solid_c9_1
result = _cut(result, cut_9)

# Cut operation 10
plane_c10_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c10_1 = cq.Workplane(plane_c10_1)
loop_c10_1 = sketch_c10_1.moveTo(-0.08145, 0.23889)
loop_c10_1 = loop_c10_1.lineTo(-0.04979, 0.27058)
loop_c10_1 = loop_c10_1.lineTo(-0.02518, 0.29352)
loop_c10_1 = loop_c10_1.lineTo(-0.00249, 0.28102)
loop_c10_1 = loop_c10_1.lineTo(0.0397, 0.2402)
loop_c10_1 = loop_c10_1.lineTo(0.03926, 0.22366)
loop_c10_1 = loop_c10_1.lineTo(-0.02065, 0.16398)
loop_c10_1 = loop_c10_1.lineTo(-0.07986, 0.22368)
loop_c10_1 = loop_c10_1.lineTo(-0.08145, 0.23889)
loop_c10_1 = loop_c10_1.close()
sketch_c10_1=sketch_c10_1.add(loop_c10_1)
solid_c10_1 = sketch_c10_1.extrude(0.04)
cut_10 = solid_c10_1
result = _cut(result, cut_10)

# Cut operation 11
plane_c11_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c11_1 = cq.Workplane(plane_c11_1)
loop_c11_1 = sketch_c11_1.moveTo(-0.23312, -0.06497)
loop_c11_1 = loop_c11_1.lineTo(-0.19478, -0.02575)
loop_c11_1 = loop_c11_1.lineTo(-0.17047, -0.00026)
loop_c11_1 = loop_c11_1.threePointArc((-0.13932, -0.0317), (-0.10937, -0.06165))
loop_c11_1 = loop_c11_1.lineTo(-0.11327, -0.07898)
loop_c11_1 = loop_c11_1.lineTo(-0.16172, -0.12789)
loop_c11_1 = loop_c11_1.lineTo(-0.17778, -0.12903)
loop_c11_1 = loop_c11_1.threePointArc((-0.20488, -0.10169), (-0.23112, -0.07567))
loop_c11_1 = loop_c11_1.lineTo(-0.23312, -0.06497)
loop_c11_1 = loop_c11_1.close()
sketch_c11_1=sketch_c11_1.add(loop_c11_1)
solid_c11_1 = sketch_c11_1.extrude(0.04)
cut_11 = solid_c11_1
result = _cut(result, cut_11)

# Cut operation 12
plane_c12_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c12_1 = cq.Workplane(plane_c12_1)
loop_c12_1 = sketch_c12_1.moveTo(-0.53318, 0.08873)
loop_c12_1 = loop_c12_1.lineTo(-0.4707, 0.14991)
loop_c12_1 = loop_c12_1.lineTo(-0.44619, 0.12529)
loop_c12_1 = loop_c12_1.threePointArc((-0.43498, 0.11371), (-0.42408, 0.1029))
loop_c12_1 = loop_c12_1.lineTo(-0.41079, 0.08935)
loop_c12_1 = loop_c12_1.lineTo(-0.40967, 0.07598)
loop_c12_1 = loop_c12_1.lineTo(-0.42195, 0.06404)
loop_c12_1 = loop_c12_1.threePointArc((-0.43157, 0.05374), (-0.44167, 0.04327))
loop_c12_1 = loop_c12_1.threePointArc((-0.451, 0.03361), (-0.46085, 0.02385))
loop_c12_1 = loop_c12_1.lineTo(-0.47378, 0.01955)
loop_c12_1 = loop_c12_1.threePointArc((-0.48073, 0.02631), (-0.48482, 0.02983))
loop_c12_1 = loop_c12_1.lineTo(-0.50419, 0.04703)
loop_c12_1 = loop_c12_1.lineTo(-0.53111, 0.07368)
loop_c12_1 = loop_c12_1.lineTo(-0.53318, 0.08873)
loop_c12_1 = loop_c12_1.close()
sketch_c12_1=sketch_c12_1.add(loop_c12_1)
solid_c12_1 = sketch_c12_1.extrude(0.04)
cut_12 = solid_c12_1
result = _cut(result, cut_12)

# Cut operation 13
plane_c13_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c13_1 = cq.Workplane(plane_c13_1)
loop_c13_1 = sketch_c13_1.moveTo(-0.5334, -0.2146)
loop_c13_1 = loop_c13_1.lineTo(-0.49871, -0.17892)
loop_c13_1 = loop_c13_1.lineTo(-0.47109, -0.15041)
loop_c13_1 = loop_c13_1.lineTo(-0.40872, -0.21374)
loop_c13_1 = loop_c13_1.threePointArc((-0.40864, -0.22183), (-0.40999, -0.22494))
loop_c13_1 = loop_c13_1.threePointArc((-0.43815, -0.2534), (-0.46417, -0.27962))
loop_c13_1 = loop_c13_1.threePointArc((-0.47563, -0.28095), (-0.47731, -0.27917))
loop_c13_1 = loop_c13_1.threePointArc((-0.48799, -0.26867), (-0.49842, -0.25894))
loop_c13_1 = loop_c13_1.threePointArc((-0.50686, -0.25083), (-0.51535, -0.24226))
loop_c13_1 = loop_c13_1.lineTo(-0.53118, -0.22634)
loop_c13_1 = loop_c13_1.lineTo(-0.5334, -0.2146)
loop_c13_1 = loop_c13_1.close()
sketch_c13_1=sketch_c13_1.add(loop_c13_1)
solid_c13_1 = sketch_c13_1.extrude(0.04)
cut_13 = solid_c13_1
result = _cut(result, cut_13)

# Cut operation 14
plane_c14_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c14_1 = cq.Workplane(plane_c14_1)
loop_c14_1 = sketch_c14_1.moveTo(-0.08085, -0.21054)
loop_c14_1 = loop_c14_1.lineTo(-0.05359, -0.18364)
loop_c14_1 = loop_c14_1.lineTo(-0.02557, -0.15743)
loop_c14_1 = loop_c14_1.lineTo(-0.01475, -0.15686)
loop_c14_1 = loop_c14_1.lineTo(0.02162, -0.19328)
loop_c14_1 = loop_c14_1.lineTo(0.03921, -0.21033)
loop_c14_1 = loop_c14_1.lineTo(0.03922, -0.22667)
loop_c14_1 = loop_c14_1.lineTo(0.00251, -0.2636)
loop_c14_1 = loop_c14_1.lineTo(-0.02075, -0.28652)
loop_c14_1 = loop_c14_1.lineTo(-0.04439, -0.26278)
loop_c14_1 = loop_c14_1.lineTo(-0.0635, -0.2427)
loop_c14_1 = loop_c14_1.lineTo(-0.08194, -0.22391)
loop_c14_1 = loop_c14_1.lineTo(-0.08085, -0.21054)
loop_c14_1 = loop_c14_1.close()
sketch_c14_1=sketch_c14_1.add(loop_c14_1)
solid_c14_1 = sketch_c14_1.extrude(0.04)
cut_14 = solid_c14_1
result = _cut(result, cut_14)

# Cut operation 15
plane_c15_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c15_1 = cq.Workplane(plane_c15_1)
loop_c15_1 = sketch_c15_1.moveTo(-0.23314, -0.21476)
loop_c15_1 = loop_c15_1.lineTo(-0.18801, -0.16864)
loop_c15_1 = loop_c15_1.lineTo(-0.17055, -0.15049)
loop_c15_1 = loop_c15_1.lineTo(-0.11061, -0.211)
loop_c15_1 = loop_c15_1.lineTo(-0.10871, -0.22405)
loop_c15_1 = loop_c15_1.lineTo(-0.14077, -0.25601)
loop_c15_1 = loop_c15_1.lineTo(-0.16342, -0.27948)
loop_c15_1 = loop_c15_1.threePointArc((-0.17395, -0.28115), (-0.17467, -0.28077))
loop_c15_1 = loop_c15_1.threePointArc((-0.2034, -0.25343), (-0.23028, -0.22656))
loop_c15_1 = loop_c15_1.threePointArc((-0.23254, -0.22016), (-0.23313, -0.21487))
loop_c15_1 = loop_c15_1.close()
sketch_c15_1=sketch_c15_1.add(loop_c15_1)
solid_c15_1 = sketch_c15_1.extrude(0.04)
cut_15 = solid_c15_1
result = _cut(result, cut_15)

# Cut operation 16
plane_c16_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c16_1 = cq.Workplane(plane_c16_1)
loop_c16_1 = sketch_c16_1.moveTo(-0.38342, -0.2209)
loop_c16_1 = loop_c16_1.lineTo(-0.38106, -0.2106)
loop_c16_1 = loop_c16_1.threePointArc((-0.35594, -0.1855), (-0.33135, -0.16086))
loop_c16_1 = loop_c16_1.lineTo(-0.31251, -0.15845)
loop_c16_1 = loop_c16_1.lineTo(-0.27707, -0.19613)
loop_c16_1 = loop_c16_1.lineTo(-0.25835, -0.21517)
loop_c16_1 = loop_c16_1.threePointArc((-0.26268, -0.22789), (-0.26586, -0.23116))
loop_c16_1 = loop_c16_1.threePointArc((-0.2941, -0.25943), (-0.32087, -0.28674))
loop_c16_1 = loop_c16_1.lineTo(-0.34348, -0.26397)
loop_c16_1 = loop_c16_1.lineTo(-0.35282, -0.25345)
loop_c16_1 = loop_c16_1.lineTo(-0.38256, -0.22319)
loop_c16_1 = loop_c16_1.close()
sketch_c16_1=sketch_c16_1.add(loop_c16_1)
solid_c16_1 = sketch_c16_1.extrude(0.04)
cut_16 = solid_c16_1
result = _cut(result, cut_16)

# Cut operation 17
plane_c17_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c17_1 = cq.Workplane(plane_c17_1)
loop_c17_1 = sketch_c17_1.moveTo(-0.61001, 0.37101)
loop_c17_1 = loop_c17_1.lineTo(-0.59899, 0.37282)
loop_c17_1 = loop_c17_1.lineTo(-0.58787, 0.38285)
loop_c17_1 = loop_c17_1.lineTo(-0.56819, 0.38328)
loop_c17_1 = loop_c17_1.lineTo(-0.55453, 0.37406)
loop_c17_1 = loop_c17_1.lineTo(-0.5436, 0.3664)
loop_c17_1 = loop_c17_1.lineTo(-0.54023, 0.34267)
loop_c17_1 = loop_c17_1.lineTo(-0.54387, 0.32593)
loop_c17_1 = loop_c17_1.lineTo(-0.549, 0.3107)
loop_c17_1 = loop_c17_1.lineTo(-0.58029, 0.30051)
loop_c17_1 = loop_c17_1.lineTo(-0.60435, 0.30811)
loop_c17_1 = loop_c17_1.lineTo(-0.61845, 0.33429)
loop_c17_1 = loop_c17_1.lineTo(-0.62207, 0.3541)
loop_c17_1 = loop_c17_1.lineTo(-0.61001, 0.37101)
loop_c17_1 = loop_c17_1.close()
sketch_c17_1=sketch_c17_1.add(loop_c17_1)
solid_c17_1 = sketch_c17_1.extrude(0.04)
cut_17 = solid_c17_1
result = _cut(result, cut_17)

# Cut operation 18
plane_c18_1 = cq.Plane(origin=(0.0, 0.0, 0.1397), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c18_1 = cq.Workplane(plane_c18_1)
loop_c18_1 = sketch_c18_1.moveTo(-0.62209, -0.3475)
loop_c18_1 = loop_c18_1.lineTo(-0.61302, -0.31408)
loop_c18_1 = loop_c18_1.lineTo(-0.59812, -0.3082)
loop_c18_1 = loop_c18_1.lineTo(-0.58144, -0.29392)
loop_c18_1 = loop_c18_1.lineTo(-0.56967, -0.30237)
loop_c18_1 = loop_c18_1.lineTo(-0.55011, -0.31332)
loop_c18_1 = loop_c18_1.lineTo(-0.54463, -0.32417)
loop_c18_1 = loop_c18_1.lineTo(-0.53677, -0.33834)
loop_c18_1 = loop_c18_1.lineTo(-0.53995, -0.3534)
loop_c18_1 = loop_c18_1.threePointArc((-0.54691, -0.36502), (-0.54795, -0.36674))
loop_c18_1 = loop_c18_1.lineTo(-0.55987, -0.38088)
loop_c18_1 = loop_c18_1.lineTo(-0.58352, -0.38172)
loop_c18_1 = loop_c18_1.lineTo(-0.60022, -0.37841)
loop_c18_1 = loop_c18_1.lineTo(-0.61688, -0.35841)
loop_c18_1 = loop_c18_1.lineTo(-0.62209, -0.3475)
loop_c18_1 = loop_c18_1.close()
sketch_c18_1=sketch_c18_1.add(loop_c18_1)
solid_c18_1 = sketch_c18_1.extrude(0.05)
cut_18 = solid_c18_1
result = _cut(result, cut_18)

# Cut operation 19
plane_c19_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c19_1 = cq.Workplane(plane_c19_1)
loop_c19_1 = sketch_c19_1.moveTo(0.06251, -0.32991)
loop_c19_1 = loop_c19_1.lineTo(0.06511, -0.31887)
loop_c19_1 = loop_c19_1.lineTo(0.08147, -0.30925)
loop_c19_1 = loop_c19_1.lineTo(0.09472, -0.30057)
loop_c19_1 = loop_c19_1.lineTo(0.11653, -0.30298)
loop_c19_1 = loop_c19_1.lineTo(0.14356, -0.32842)
loop_c19_1 = loop_c19_1.lineTo(0.14353, -0.35029)
loop_c19_1 = loop_c19_1.lineTo(0.1376, -0.36887)
loop_c19_1 = loop_c19_1.lineTo(0.12427, -0.37546)
loop_c19_1 = loop_c19_1.lineTo(0.1022, -0.38021)
loop_c19_1 = loop_c19_1.lineTo(0.0895, -0.38066)
loop_c19_1 = loop_c19_1.lineTo(0.07905, -0.37296)
loop_c19_1 = loop_c19_1.lineTo(0.06309, -0.35943)
loop_c19_1 = loop_c19_1.lineTo(0.0631, -0.33147)
loop_c19_1 = loop_c19_1.close()
sketch_c19_1=sketch_c19_1.add(loop_c19_1)
solid_c19_1 = sketch_c19_1.extrude(0.05)
cut_19 = solid_c19_1
result = _cut(result, cut_19)

# Cut operation 20
plane_c20_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c20_1 = cq.Workplane(plane_c20_1)
loop_c20_1 = sketch_c20_1.moveTo(0.06194, 0.3511)
loop_c20_1 = loop_c20_1.threePointArc((0.06563, 0.3575), (0.06895, 0.36376))
loop_c20_1 = loop_c20_1.lineTo(0.07628, 0.3774)
loop_c20_1 = loop_c20_1.lineTo(0.09674, 0.38194)
loop_c20_1 = loop_c20_1.lineTo(0.11263, 0.38111)
loop_c20_1 = loop_c20_1.lineTo(0.13243, 0.37008)
loop_c20_1 = loop_c20_1.lineTo(0.14048, 0.34609)
loop_c20_1 = loop_c20_1.lineTo(0.14442, 0.33505)
loop_c20_1 = loop_c20_1.lineTo(0.13325, 0.31406)
loop_c20_1 = loop_c20_1.lineTo(0.1198, 0.30298)
loop_c20_1 = loop_c20_1.lineTo(0.1076, 0.30147)
loop_c20_1 = loop_c20_1.lineTo(0.07757, 0.30458)
loop_c20_1 = loop_c20_1.lineTo(0.06412, 0.32453)
loop_c20_1 = loop_c20_1.threePointArc((0.06294, 0.33753), (0.06199, 0.35101))
loop_c20_1 = loop_c20_1.close()
sketch_c20_1=sketch_c20_1.add(loop_c20_1)
solid_c20_1 = sketch_c20_1.extrude(0.04)
cut_20 = solid_c20_1
result = _cut(result, cut_20)

# Cut operation 21
plane_c21_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c21_1 = cq.Workplane(plane_c21_1)
loop_c21_1 = sketch_c21_1.moveTo(-0.5697, 0.9213)
loop_c21_1 = loop_c21_1.circle(0.02495)
sketch_c21_1=sketch_c21_1.add(loop_c21_1)
solid_c21_1 = sketch_c21_1.extrude(0.04)
cut_21 = solid_c21_1
result = _cut(result, cut_21)

# Cut operation 22
plane_c22_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c22_1 = cq.Workplane(plane_c22_1)
loop_c22_1 = sketch_c22_1.moveTo(-0.5779, -0.89945)
loop_c22_1 = loop_c22_1.lineTo(-0.56017, -0.8958)
loop_c22_1 = loop_c22_1.lineTo(-0.54806, -0.93693)
loop_c22_1 = loop_c22_1.lineTo(-0.56122, -0.94617)
loop_c22_1 = loop_c22_1.lineTo(-0.5779, -0.89945)
loop_c22_1 = loop_c22_1.close()
sketch_c22_1=sketch_c22_1.add(loop_c22_1)
solid_c22_1 = sketch_c22_1.extrude(0.04)
cut_22 = solid_c22_1
result = _cut(result, cut_22)

# Cut operation 23
plane_c23_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c23_1 = cq.Workplane(plane_c23_1)
loop_c23_1 = sketch_c23_1.moveTo(0.5695, -0.92094)
loop_c23_1 = loop_c23_1.circle(0.02478)
sketch_c23_1=sketch_c23_1.add(loop_c23_1)
solid_c23_1 = sketch_c23_1.extrude(0.04)
cut_23 = solid_c23_1
result = _cut(result, cut_23)

# Cut operation 24
plane_c24_1 = cq.Plane(origin=(0.0, 0.0, 0.1497), normal=(0.0, 0.0, 1.0), xDir=(0.0, 1.0, 0.0))
sketch_c24_1 = cq.Workplane(plane_c24_1)
loop_c24_1 = sketch_c24_1.moveTo(0.5698, 0.9213)
loop_c24_1 = loop_c24_1.circle(0.02447)
sketch_c24_1=sketch_c24_1.add(loop_c24_1)
solid_c24_1 = sketch_c24_1.extrude(0.04)
cut_24 = solid_c24_1
result = _cut(result, cut_24)
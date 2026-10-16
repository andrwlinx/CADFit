"""Synthetic parts with known CAD for the agent-skill tests (tests/meshes/*.stl).

  .venv/bin/python tests/make_test_meshes.py
"""
import os

import cadquery as cq

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'meshes')

PARTS = {
    # Extrusion with a through hole: one Z sketch (outer + hole) extruded.
    'plate_hole': cq.Workplane('XY').box(2.0, 1.2, 0.3).faces('>Z').workplane().hole(0.5),
    # Revolve: stepped shaft along Z.
    'shaft': (cq.Workplane('XZ').polyline([(0, 0), (0.6, 0), (0.6, 0.5), (0.35, 0.5), (0.35, 1.6), (0, 1.6)])
              .close().revolve(360, (0, 0, 0), (0, 1, 0))),
    # Two extrusions along different axes: an L-bracket (section_extrude along Y recovers it whole).
    'bracket': (cq.Workplane('XZ').polyline([(0, 0), (1.6, 0), (1.6, 0.25), (0.25, 0.25), (0.25, 1.2), (0, 1.2)])
                .close().extrude(-0.9)),
}


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, wp in PARTS.items():
        cq.exporters.export(wp, os.path.join(OUT, f'{name}.stl'), tolerance=0.002, angularTolerance=0.05)
        print('wrote', name)


if __name__ == '__main__':
    main()

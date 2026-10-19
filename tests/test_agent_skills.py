"""Acceptance checks for agent/skills.py on synthetic parts with known geometry.

  .venv/bin/python -m pytest -q tests/test_agent_skills.py
"""
import os
import sys

import numpy as np
import pytest
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'agent'))
from skills import SkillWorkspace  # noqa: E402

MESHES = os.path.join(HERE, 'meshes')


def ws(name, tmp_path):
    return SkillWorkspace(os.path.join(MESHES, f'{name}.stl'), str(tmp_path / 'work'))


def section_area(w, normal, offset):
    """Net cross-section area of the (normalized) target, independent of the skill code."""
    n = np.asarray(normal, float)
    s = w.gt_mesh.section(plane_origin=n * offset, plane_normal=n)
    return sum(p.area for p in s.to_planar()[0].polygons_full)


def test_directions_axis_aligned(tmp_path):
    out = ws('bracket', tmp_path).detect_directions()
    assert len(out['axes']) == 3
    assert out['other_directions'] == []  # every wall is parallel to an axis


def test_directions_rotated(tmp_path):
    # Bracket extruded along Y, turned 30 degrees about Z: the extrusion direction is off-axis.
    m = trimesh.load(os.path.join(MESHES, 'bracket.stl'))
    m.apply_transform(trimesh.transformations.rotation_matrix(np.radians(30), [0, 0, 1]))
    path = str(tmp_path / 'bracket_rot.stl')
    m.export(path)
    out = SkillWorkspace(path, str(tmp_path / 'work')).detect_directions()
    want = np.array([-np.sin(np.radians(30)), np.cos(np.radians(30)), 0.0])
    # The extrusion direction is also the normal of the two end caps.
    dirs = [d['direction'] for d in out['other_directions']] + [f['normal'] for f in out['flat_face_normals']]
    assert any(abs(np.dot(d, want)) > 0.999 for d in dirs)


def test_extract_plate_hole(tmp_path):
    w = ws('plate_hole', tmp_path)
    out = w.extract_sketch([0, 0, 1], 0.0)
    assert len(out['sketches']) == 1
    s = out['sketches'][0]
    assert s['n_loops'] == 2  # outer boundary + the hole
    net = s['outer_area'] - sum(s['hole_areas'])
    assert net == pytest.approx(section_area(w, [0, 0, 1], 0.0), rel=0.01)
    assert s['primitives']['lines'] >= 4 and s['primitives']['arcs'] + s['primitives']['circles'] >= 1
    # Same plane again: cached, same ids, no new sketches.
    again = w.extract_sketch('z', 0.0)
    assert [t['id'] for t in again['sketches']] == [s['id']] and len(w.sketches) == 1


def test_extract_shaft_profile(tmp_path):
    w = ws('shaft', tmp_path)
    out = w.extract_sketch([0, 1, 0], 0.0)
    assert len(out['sketches']) == 1 and out['sketches'][0]['n_loops'] == 1
    assert out['sketches'][0]['outer_area'] == pytest.approx(section_area(w, [0, 1, 0], 0.0), rel=0.01)


def test_extract_misses(tmp_path):
    out = ws('plate_hole', tmp_path).extract_sketch([0, 0, 1], 0.9)
    assert out['sketches'] == [] and 'misses' in out['note']


def test_extract_bad_normal(tmp_path):
    with pytest.raises(ValueError):
        ws('plate_hole', tmp_path).extract_sketch([0, 0, 0], 0.0)


def best_extrusion(w, normal, offset):
    sk = w.extract_sketch(normal, offset)['sketches']
    assert sk, 'no sketch'
    out = w.fit_extrude(sk[0]['id'])
    assert out['candidates'], out
    return max(out['candidates'], key=lambda c: c['iou'])


@pytest.mark.parametrize('name,normal,offset', [('plate_hole', [0, 0, 1], 0.0), ('bracket', [0, 1, 0], 0.0)])
def test_extrude_recovers_part(tmp_path, name, normal, offset):
    w = ws(name, tmp_path)
    best = best_extrusion(w, normal, offset)
    assert best['iou'] > 0.98 and best['precision'] > 0.98
    # Into the model, then the exported CadQuery program rebuilds it.
    assert w.add_candidate(best['id'])['iou_after'] > 0.98
    w.export(str(tmp_path / 'out'))
    import subprocess
    r = subprocess.run([sys.executable, 'agent_model.py'], cwd=tmp_path / 'out', capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    rebuilt = trimesh.load(str(tmp_path / 'out' / 'agent_model_cq.stl'))
    assert rebuilt.volume == pytest.approx(w.best[1][0]['m'].volume(), rel=0.01)


def test_extrude_is_cached(tmp_path):
    w = ws('plate_hole', tmp_path)
    sid = w.extract_sketch([0, 0, 1], 0.0)['sketches'][0]['id']
    first = w.fit_extrude(sid)['candidates']
    assert w.fit_extrude(sid)['candidates'] == first and len(w.candidates) == len(first)


def test_extrude_unknown_sketch(tmp_path):
    assert 'error' in ws('plate_hole', tmp_path).fit_extrude('S9')


def test_revolve_recovers_shaft(tmp_path):
    w = ws('shaft', tmp_path)
    sid = w.extract_sketch([0, 1, 0], 0.0)['sketches'][0]['id']
    out = w.fit_revolve(sid)
    assert out['candidates'], out
    best = max(out['candidates'], key=lambda c: c['iou'])
    assert best['iou'] > 0.97
    assert abs(best['axis_direction'][2]) > 0.999  # the shaft's axis is Z


def test_revolve_recovers_offset_shaft(tmp_path):
    """Shaft whose axis plane is not through the origin (y = -0.35 after normalization)."""
    w = ws('shaft_offset', tmp_path)
    raw = trimesh.load(os.path.join(MESHES, 'shaft_offset.stl'), force='mesh')
    lo, hi = raw.bounds
    y_axis = float((0.0 - 0.5 * (lo[1] + hi[1])) * 2.0 / (hi - lo).max())  # source axis y = 0, normalized
    sk = w.extract_sketch([0, 1, 0], y_axis)['sketches']
    sid = max(sk, key=lambda s: s['outer_area'])['id']
    out = w.fit_revolve(sid)
    assert out['candidates'], out
    best = max(out['candidates'], key=lambda c: c['precision'] * c['coverage'])
    assert best['precision'] > 0.97, best          # the revolved shaft lies inside the target
    assert abs(best['axis_point'][1] - y_axis) < 0.02, best  # axis lies in the sketch plane


def test_section_extrude_bracket(tmp_path):
    w = ws('bracket', tmp_path)
    out = w.section_extrude('y')
    assert len(out['candidates']) == 1 and out['candidates'][0]['iou'] > 0.98
    assert w.section_extrude('y')['candidates'] == out['candidates']  # cached
    assert w.section_extrude('y', 5.0)['candidates'] == []           # plane misses the part


def test_toolsets(tmp_path):
    import json
    import subprocess
    root = os.path.dirname(HERE)
    script = tmp_path / 'calls.json'
    script.write_text(json.dumps([[{'name': 'section_extrude', 'arguments': {'axis': 'y'}}],
                                  [{'name': 'add_code', 'arguments': {'code': "result = cq.Workplane('XY').box(1,1,1)"}}]]))
    for toolset, ok in (('skills', True), ('code', False)):
        out = tmp_path / toolset
        r = subprocess.run([sys.executable, os.path.join(root, 'agent', 'agent_loop.py'), '--toolset', toolset,
                            '--model', f'scripted:{script}', '--gt', os.path.join(MESHES, 'bracket.stl'),
                            '--out', str(out)], capture_output=True, text=True, cwd=root)
        assert r.returncode == 0, r.stderr[-800:]
        tool_msgs = [json.loads(ln) for ln in open(out / 'transcript.jsonl') if '"role": "tool"' in ln]
        first = json.loads(tool_msgs[0]['content'])
        # The code toolset must not reach a CADFit skill even when the model names it.
        assert ('error' not in first) == ok, first
        # Agent code runs in the sandbox and builds (workdir under the pytest tmp dir).
        added = json.loads(tool_msgs[1]['content'])
        assert 'error' not in added and added['iou_after'] > 0, added
        assert json.load(open(out / 'result.json'))['toolset'] == toolset


def test_island_inside_hole(tmp_path):
    # A ring with a separate disc sitting inside its hole: the disc is material, not a second hole.
    import cadquery as cq
    ring = cq.Workplane('XY').circle(1.0).circle(0.7).extrude(0.2)
    disc = cq.Workplane('XY').circle(0.4).extrude(0.2)
    path = str(tmp_path / 'ring_disc.stl')
    cq.exporters.export(ring.union(disc), path, tolerance=0.002, angularTolerance=0.05)
    w = SkillWorkspace(path, str(tmp_path / 'work'))
    out = w.extract_sketch([0, 0, 1], 0.0)['sketches']
    assert len(out) == 2
    assert out[0]['n_loops'] == 2 and out[1]['n_loops'] == 1  # ring (outer + hole), then the disc
    net = sum(s['outer_area'] - sum(s['hole_areas']) for s in out)
    assert net == pytest.approx(section_area(w, [0, 0, 1], 0.0), rel=0.01)


def test_offset_is_distance_along_unit_normal(tmp_path):
    w = ws('plate_hole', tmp_path)
    a = w.extract_sketch([0, 0, 2], 0.1)['sketches']
    b = w.extract_sketch([0, 0, 1], 0.1)['sketches']
    assert [s['id'] for s in a] == [s['id'] for s in b]  # same plane z = 0.1, served from the cache

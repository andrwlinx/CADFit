"""Regressions for the CADFit++ v2 review (run_20261019_e1c2d949, round 1).

  .venv/bin/python -m pytest -q tests/test_v2_fixes.py
"""
import os
import sys
import time

import numpy as np
import pytest
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'agent'))
import cad_tools  # noqa: E402
import cadquery_ops  # noqa: E402
import exec_verify  # noqa: E402
import skills  # noqa: E402
from fit_primitives import _arc_degenerate  # noqa: E402

MESHES = os.path.join(HERE, 'meshes')


# ---------- exec cache (finding 1) ----------
def test_exec_cache_after_remove_matches_fresh_execution(tmp_path, monkeypatch):
    """add / add / remove / add: the reply must describe the program now assembled
    (the id()-keyed cache could return the removed step's record)."""
    monkeypatch.setattr(cad_tools, 'EXEC', True)
    ws = cad_tools.CadWorkspace(os.path.join(MESHES, 'plate_hole.stl'), str(tmp_path / 'w'))
    big = "result = cq.Workplane('XY').box(2.0, 1.2, 0.3)\n"
    ws.add_code(big)
    bad = ws.add_code("result = cq.Workplane('XY').box(0.2, 0.2, 0.2).translate((3, 0, 0))\n")
    ws.remove_step(bad['step'])
    good = ws.add_code("result = cq.Workplane('XY').box(0.5, 0.5, 0.3)\n", mode='cut')
    ws._exec_cache.clear()
    fresh = ws._exec()
    assert abs(good['program_iou'] - round(fresh['iou'], 4)) < 1e-4, (good, fresh)


def test_answer_metadata_describes_delivered_program(tmp_path, monkeypatch):
    monkeypatch.setattr(cad_tools, 'EXEC', True)
    ws = cad_tools.CadWorkspace(os.path.join(MESHES, 'plate_hole.stl'), str(tmp_path / 'w'))
    ws.add_code("result = cq.Workplane('XY').box(2.0, 1.2, 0.3)\n")
    assert ws.answer_steps() is ws.best_exec[1]


# ---------- exec_verify selection (finding 2) ----------
def test_choose_prefers_any_valid_program():
    recs = {'original': {'built': True, 'valid': False, 'iou_exec': 0.99},
            'fused': {'built': True, 'valid': True, 'iou_exec': 0.90},
            'single': {'built': True, 'valid': True, 'iou_exec': 0.60}}
    assert exec_verify.choose(recs) == 'fused'


def test_choose_without_valid_programs_takes_best_built():
    recs = {'original': {'built': True, 'valid': False, 'iou_exec': 0.7},
            'fused': {'built': False, 'valid': False, 'iou_exec': 0.0}}
    assert exec_verify.choose(recs) == 'original'
    assert exec_verify.choose({'a': {'built': False}}) is None


# ---------- deadline (finding 3) ----------
def test_session_timeout_is_not_swallowed_by_generic_handlers():
    """Geometry stages catch Exception and continue; the deadline must still stop the call."""
    def stage():
        for _ in range(200):
            try:
                time.sleep(0.01)
            except Exception:  # what greedy_search's axis refinement does
                pass
        return 'finished'
    t0 = time.time()
    res, err = cad_tools.run_until(time.time() + 0.1, stage)
    assert res is None and 'time limit' in err
    assert time.time() - t0 < 0.5


def test_run_until_past_deadline_does_not_call():
    called = []
    res, err = cad_tools.run_until(time.time() - 1, lambda: called.append(1))
    assert err and not called


# ---------- revolve emission (finding 4) ----------
def _revolve_script(actions, x_axis):
    return cadquery_ops.generate_cadquery_revolve_script(
        actions, (x_axis, 0.0, 0.0), (x_axis, 1.0, 0.0), 360.0, '/tmp/unused.stl',
        origin=(0, 0, 0), normal=(0, 0, 1), xdir=(1, 0, 0))


def test_revolve_rejects_circle_crossing_axis():
    """00941601 refine sketch 9: a fitted r=112.7 circle whose leftmost point is
    1.06e-3 past the axis (only the circle centre was checked before)."""
    actions = ['sketch.moveTo(112.98129, 0.5)', 'sketch.circle(112.68804)']
    assert 'raise ValueError' in _revolve_script(actions, 0.294312)


def test_revolve_rejects_arc_bulging_across_axis():
    # Half profile whose closing arc's end points are on the axis but whose middle bulges 0.05 across.
    actions = ['sketch.moveTo(0.0, 0.0)', 'sketch.lineTo(0.5, 0.0)', 'sketch.lineTo(0.5, 1.0)',
               'sketch.lineTo(0.0, 1.0)', 'sketch = sketch.threePointArc((-0.05, 0.5), (0.0, 0.0))']
    assert 'raise ValueError' in _revolve_script(actions, 0.0)


def test_revolve_on_axis_profile_builds():
    """Split profile with its closing edge on the axis (within rounding): accepted and builds."""
    import cadquery as cq
    actions = ['sketch.moveTo(0.00003, 0.0)', 'sketch.lineTo(0.5, 0.0)', 'sketch.lineTo(0.5, 1.0)',
               'sketch.lineTo(-0.00002, 1.0)', 'sketch.close()']
    script = _revolve_script(actions, 0.0)
    assert 'raise ValueError' not in script
    ns = {'cq': cq}
    exec(script.replace("cq.exporters.export(result, '/tmp/unused.stl')", ''), ns)
    vol = ns['result'].val().Volume()
    assert abs(vol - np.pi * 0.25) < 0.01 * np.pi * 0.25


def test_revolve_recovers_rotated_translated_shaft(tmp_path, monkeypatch):
    """Shaft about an oblique axis away from the origin: the v2 revolve hint gives the
    slice containing the axis, and fit_revolve must rebuild the shaft there."""
    import cadquery as cq
    shaft = (cq.Workplane('XZ').polyline([(0, 0), (0.6, 0), (0.6, 0.5), (0.35, 0.5), (0.35, 1.6), (0, 1.6)])
             .close().revolve(360, (0, 0, 0), (0, 1, 0))
             .rotate((0, 0, 0), (1, 0, 0), 35).rotate((0, 0, 0), (0, 0, 1), 20).translate((0.3, -0.2, 0.1)))
    stl = str(tmp_path / 'shaft_rot.stl')
    cq.exporters.export(shaft, stl, tolerance=0.002, angularTolerance=0.05)
    monkeypatch.setattr(skills, '_EXEC', True)
    w = skills.SkillWorkspace(stl, str(tmp_path / 'work'))
    hints = w._revolve_hints()['revolve_axes']
    assert hints, 'no revolve axis found for a shaft'
    h = hints[0]
    sk = w.extract_sketch(h['slice_containing_axis']['normal'], h['slice_containing_axis']['offset'])['sketches']
    sid = max(sk, key=lambda s: s['outer_area'])['id']
    # The sketch's own axis search tries only its plane's 0°/90° directions: no axis here.
    assert not w.fit_revolve(sid)['candidates']
    out = w.fit_revolve(sid, axis_point=h['axis_point'], axis_direction=h['axis_direction'])
    assert out['candidates'], out
    best = max(out['candidates'], key=lambda c: c['precision'] * c['coverage'])
    assert best['precision'] > 0.95 and best['coverage'] > 0.95, best
    assert abs(np.dot(best['axis_direction'], h['axis_direction'])) > 0.99, (best, h)


# ---------- degenerate arcs ----------
def test_collinear_arc_is_emitted_as_line():
    """00642725 sketch 1: threePointArc through collinear points, which OCC refuses."""
    import cadquery as cq
    from OCP.StdFail import StdFail_NotDone
    start, mid, end = (0.35302, -0.13224), (0.38295, -0.10231), (0.41272, -0.07254)
    assert _arc_degenerate(start, mid, end)
    with pytest.raises((StdFail_NotDone, Exception)):
        cq.Workplane('XY').moveTo(*start).threePointArc(mid, end)
    assert not _arc_degenerate((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0))


def test_repair_pass_keeps_valid_solids(tmp_path):
    """The repair suffix leaves valid solids as they are (same volume, still valid)."""
    import json
    import subprocess
    prog = tmp_path / 'p.py'
    prog.write_text("import cadquery as cq\nresult = cq.Workplane('XY').box(1, 1, 1).add("
                    "cq.Workplane('XY').box(0.5, 0.5, 2))\n" + exec_verify.REPAIR)
    r = json.loads(subprocess.run([sys.executable, os.path.join(ROOT, 'bench', 'cad_replay.py'), str(prog),
                                   str(tmp_path / 'p.stl')], capture_output=True, text=True).stdout.splitlines()[-1])
    assert r['built'] and r['valid'] and r['n_solids'] == 2, r

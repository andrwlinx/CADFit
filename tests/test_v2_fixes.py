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


# ---------- dev3/dev4 infrastructure failures ----------
def test_cq_worker_retries_after_child_death(monkeypatch):
    """A worker killed mid-script (OOM killer) costs one retry, not the candidate."""
    import cq_worker
    monkeypatch.setenv('CADFIT_CQ_WORKER', '1')
    calls = []

    def run(script, path=None, timeout=60.0):
        calls.append(script)
        return (False, 'cq_worker died') if len(calls) == 1 else (True, '')
    monkeypatch.setattr(cq_worker._client, 'run', run)
    assert cq_worker.run_script('x = 1') == (True, '') and len(calls) == 2


def test_stalled_decimation_keeps_input_without_voxelizing(tmp_path, monkeypatch):
    """00247424: edge collapse stalls (80,168 -> 80,070 faces). The input must be kept
    as is, never sent through trimesh's subdividing voxelizer, which exhausted memory."""
    import fast_simplification
    import run_pipeline
    sphere = trimesh.creation.icosphere(subdivisions=5)  # 20,480 faces
    stl = str(tmp_path / 'stalls.stl')
    sphere.export(stl)
    monkeypatch.setattr(fast_simplification, 'simplify', lambda v, f, **k: (v, f[:-10]))
    monkeypatch.setattr(trimesh.Trimesh, 'voxelized',
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError('voxelized called')))
    assert run_pipeline._decimate_input_if_needed(stl, str(tmp_path / 'out'), target_faces=1_000) == stl


def test_voxel_remesh_is_in_world_coordinates():
    pytest.importorskip('skimage')
    import run_pipeline
    box = trimesh.creation.box((2.0, 1.0, 0.5))
    box.apply_translation((3.0, -1.0, 0.2))
    r = run_pipeline._voxel_remesh(box, 0.05)
    assert np.allclose(r.bounds, box.bounds, atol=0.1), (r.bounds, box.bounds)
    assert abs(r.volume / box.volume - 1) < 0.25


def test_judge_does_not_alpha_wrap_open_ground_truth(tmp_path):
    """00966049: a GT STL that is not watertight must not take the exact path (its
    alpha wrap is a fatter solid); the winding-number estimate judges it."""
    sys.path.insert(0, os.path.join(ROOT, 'bench'))
    import score
    plate = trimesh.creation.box((2.0, 1.3, 0.1))
    gt = trimesh.Trimesh(plate.vertices, plate.faces[:-1], process=False)  # one triangle missing
    assert not gt.is_watertight
    gt.export(str(tmp_path / 'gt.stl'))
    plate.export(str(tmp_path / 'rc.stl'))
    j = score.robust_iou(str(tmp_path / 'gt.stl'), str(tmp_path / 'rc.stl'))
    assert j['method'] == 'gwn-mc' and j['iou'] > 0.97, j


@pytest.mark.parametrize('th', [0.0063, 0.012, 0.037, 0.4137])
def test_precise_extents_match_plate_thickness(monkeypatch, th):
    # Stock sweeps [-2, 2] by 0.01 and widens interval ends by one step: a 0.037
    # plate comes out 0.04 thick and plates under ~0.02 are not proposed at all.
    import trimesh
    import analyze_loop_translation as alt
    monkeypatch.setenv('CADFIT_FAST_CD', '1')
    box = trimesh.creation.box((2.0, 1.4, th))
    np.random.seed(0)
    pts = box.sample(100000)
    t = np.linspace(0, 1, 200, endpoint=False)
    sq = np.concatenate([np.c_[-1 + 2 * t, -0.7 + 0 * t], np.c_[1 + 0 * t, -0.7 + 1.4 * t],
                         np.c_[1 - 2 * t, 0.7 + 0 * t], np.c_[-1 + 0 * t, 0.7 - 1.4 * t]])
    entry = {'loops_3d': [np.c_[sq, np.full(len(sq), -th / 2)].tolist()], 'normal': [0, 0, 1]}
    args = (0, entry, pts, {'vertices': box.vertices, 'faces': box.faces}, '/tmp', (-2.0, 2.0), 0.01, False)
    monkeypatch.setenv('CADFIT_PRECISE_EXTENTS', '1')
    iv = alt.process_single_sketch(args)['intervals']['merged_intervals']
    assert len(iv) == 1
    assert iv[0]['t_start'] == pytest.approx(0.0, abs=1e-6) and iv[0]['t_end'] == pytest.approx(th, abs=1e-6)
    monkeypatch.setenv('CADFIT_PRECISE_EXTENTS', '0')
    stock = alt.process_single_sketch(args)['intervals'].get('merged_intervals', [])
    if th < 0.02:
        assert stock == []


def test_surface_agreement_recall_precision(tmp_path):
    # CAD = target plus a slab of extra material: recall stays 1, precision drops.
    import trimesh
    sys.path.insert(0, os.path.join(ROOT, 'bench'))
    import detail_scores
    gt = trimesh.creation.box((2.0, 1.0, 0.5))
    extra = trimesh.creation.box((2.0, 1.0, 0.5))
    extra.apply_translation((0, 0, 0.25 + 0.25))  # stacked on top: doubles the height
    cad = trimesh.util.concatenate([gt, extra])
    gp, cp = str(tmp_path / 'gt.stl'), str(tmp_path / 'cad.stl')
    gt.export(gp)
    cad.export(cp)  # the gt is centered with largest extent 2, so its normalized frame is the identity
    d = detail_scores.detail(gp, cp, n_cad=400_000)
    sw = d['sweep']['0.01']
    assert sw['recall'] > 0.95
    assert sw['precision'] < 0.85
    assert abs(sw['fscore'] - 2 * sw['recall'] * sw['precision'] / (sw['recall'] + sw['precision'])) < 1e-12

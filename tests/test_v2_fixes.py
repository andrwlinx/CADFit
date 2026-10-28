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


def test_executed_score_is_the_judge_and_sections_show_the_program(tmp_path, monkeypatch):
    # The kept answer is ranked by bench/score.py's judge, and model sections draw
    # the executed program (the geometry evaluate() reports), not the step meshes.
    sys.path.insert(0, os.path.join(ROOT, 'bench'))
    import score
    monkeypatch.setattr(cad_tools, 'EXEC', True)
    gt = os.path.join(MESHES, 'plate_hole.stl')
    ws = cad_tools.CadWorkspace(gt, str(tmp_path / 'w'))
    ws.add_code("result = cq.Workplane('XY').box(2.0, 1.2, 0.3)\n")
    r = ws._exec()
    assert r['iou'] == pytest.approx(score.robust_iou(gt, r['_stl'])['iou'], abs=1e-9)
    sec = ws.section('z', 0.0)
    assert sec['model_source'] == 'executed program' and sec['model']


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
def test_precise_extents_match_plate_thickness(tmp_path, monkeypatch, th):
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
    args = (0, entry, pts, {'vertices': box.vertices, 'faces': box.faces}, str(tmp_path), (-2.0, 2.0), 0.01, False)
    monkeypatch.setenv('CADFIT_PRECISE_EXTENTS', '1')
    iv = alt.process_single_sketch(args)['intervals']['merged_intervals']
    assert len(iv) == 1
    assert iv[0]['t_start'] == pytest.approx(0.0, abs=1e-6) and iv[0]['t_end'] == pytest.approx(th, abs=1e-6)
    monkeypatch.setenv('CADFIT_PRECISE_EXTENTS', '0')
    stock = alt.process_single_sketch(args)['intervals'].get('merged_intervals', [])
    if th < 0.02:
        assert stock == []


def test_surface_agreement_is_representation_invariant(tmp_path):
    # The same occupied volume (a 2 x 1 x 1 block) given as one box and as the target
    # block plus a slab stacked on it (a buried face between them) scores the same:
    # the target's top face is inside the CAD in both, so recall drops to ~1 - its share.
    import trimesh
    sys.path.insert(0, os.path.join(ROOT, 'bench'))
    import detail_scores
    gt = trimesh.creation.box((2.0, 1.0, 0.5))
    slab = trimesh.creation.box((2.0, 1.0, 0.5))
    slab.apply_translation((0, 0, 0.5))
    single = trimesh.creation.box((2.0, 1.0, 1.0))
    single.apply_translation((0, 0, 0.25))
    gp = str(tmp_path / 'gt.stl')
    gt.export(gp)
    out = {}
    for name, cad in (('stacked', trimesh.util.concatenate([gt, slab])), ('single', single)):
        cp = str(tmp_path / f'{name}.stl')
        cad.export(cp)
        out[name] = detail_scores.detail(gp, cp)['sweep']['0.01']
    for k in ('recall', 'precision', 'fscore'):
        assert out['stacked'][k] == pytest.approx(out['single'][k], abs=0.01), (k, out)
    top_share = 2.0 / gt.area  # the target's top face lies inside the CAD
    assert out['single']['recall'] == pytest.approx(1 - top_share, abs=0.02)


def test_early_fallback_delivers_executed_section(tmp_path):
    # A part whose analysis stops before the search still gets a checked answer.
    import json
    import trimesh
    import run_pipeline
    ring = trimesh.creation.annulus(r_min=0.3, r_max=1.0, height=0.4, sections=64)
    stl = str(tmp_path / 'ring.stl')
    ring.export(stl)
    out = tmp_path / 'out'
    out.mkdir()
    run_pipeline._early_fallback('ring', stl, stl, str(out), time.time(), 'analysis failed')
    rec = json.load(open(out / 'final_iou.json'))
    ev = rec['exec_verify']
    assert ev['early_fallback'] == 'analysis failed'
    assert ev['chosen'] == 'original' or ev['chosen'].startswith('section_')
    assert ev['chosen_valid'] and rec['final_iou'] > 0.95
    assert (out / 'best_greedy_parallel.py').exists() and (out / 'best_greedy_parallel.stl').exists()


def test_silhouette_trim_removes_material_outside_the_target(tmp_path):
    # Target: a 2 x 1 x 0.5 block. Program: the block plus a lump sticking out of its
    # top face. The trimmed variant cuts the lump off, stays valid and wins.
    import trimesh
    tgt = str(tmp_path / 'block.stl')
    trimesh.creation.box((2.0, 1.0, 0.5)).export(tgt)
    prog = tmp_path / 'prog.py'
    prog.write_text("import cadquery as cq\n"
                    "result = cq.Workplane('XY').box(2.0, 1.0, 0.5).union(\n"
                    "    cq.Workplane('XY').box(0.4, 0.4, 0.4).translate((0, 0, 0.4)))\n")
    rec = exec_verify.verify(str(prog), tgt, str(tmp_path / 'ev'), trim=True)
    trimmed = [k for k in rec['variants'] if k.endswith('_trim')]
    assert trimmed, rec['variants'].keys()
    t = rec['variants'][trimmed[0]]
    assert t['built'] and t['valid']
    assert t['iou_exec'] > 0.99 > rec['variants']['original']['iou_exec']
    assert rec['chosen'] == trimmed[0]


def test_surface_agreement_ignores_faces_buried_in_a_compound(tmp_path):
    # Two overlapping boxes whose union is exactly the target: the faces buried in
    # the union are not extra surface, so precision stays ~1.
    import trimesh
    sys.path.insert(0, os.path.join(ROOT, 'bench'))
    import detail_scores
    gt = trimesh.creation.box((2.0, 1.0, 0.5))
    a = trimesh.creation.box((1.2, 1.0, 0.5))
    a.apply_translation((-0.4, 0, 0))
    b = trimesh.creation.box((1.2, 1.0, 0.5))
    b.apply_translation((0.4, 0, 0))
    gp, cp = str(tmp_path / 'gt.stl'), str(tmp_path / 'cad.stl')
    gt.export(gp)
    trimesh.util.concatenate([a, b]).export(cp)
    d = detail_scores.detail(gp, cp, n_cad=400_000)
    assert d['sweep']['0.01']['precision'] > 0.97 and d['sweep']['0.01']['recall'] > 0.97


def test_snapped_extents_reach_candidate_generation(tmp_path, monkeypatch):
    # The search reloads sketch_<i>_intervals.json, which was written before snapping:
    # check the snapped end and the grid-end alternative through that path.
    import trimesh
    import analyze_loop_translation as alt
    import greedy_search as gs
    monkeypatch.setenv('CADFIT_FAST_CD', '1')
    monkeypatch.setenv('CADFIT_PRECISE_EXTENTS', '1')
    th = 0.4137
    box = trimesh.creation.box((2.0, 1.4, th))
    np.random.seed(0)
    pts = box.sample(100000)
    t = np.linspace(0, 1, 200, endpoint=False)
    sq = np.concatenate([np.c_[-1 + 2 * t, -0.7 + 0 * t], np.c_[1 + 0 * t, -0.7 + 1.4 * t],
                         np.c_[1 - 2 * t, 0.7 + 0 * t], np.c_[-1 + 0 * t, 0.7 - 1.4 * t]])
    entry = {'loops_3d': [np.c_[sq, np.full(len(sq), -th / 2)].tolist()], 'normal': [0, 0, 1],
             'origin': [0, 0, -th / 2], 'xdir': [1, 0, 0]}
    alt.process_single_sketch((0, entry, pts, {'vertices': box.vertices, 'faces': box.faces}, str(tmp_path),
                               (-2.0, 2.0), 0.01, False))
    data = gs.load_translation_analysis(str(tmp_path), 0)
    iv = data['merged_intervals'][0]
    assert iv['t_end'] == pytest.approx(th, abs=1e-6) and 't_end_grid' in iv
    heights = {e['source']: e['height'] for e in gs.create_extrusion_from_translation(entry, data, 0)}
    assert heights['interval_0'] == pytest.approx(th, abs=1e-6)
    assert abs(heights['interval_0_grid'] - th) > 1e-3



def test_fused_boundary_of_a_merged_compound(tmp_path):
    # The saved 00232213 repair builds 139 valid solids; after an STL roundtrip the
    # tessellation is one connected body, so body counts cannot reveal the faces
    # buried between the solids. union_replay.py fuses the solids: the boundary it
    # tessellates is closed and well under the compound's tessellated area.
    import json
    import subprocess
    import trimesh
    import cadquery as cq
    prog = os.path.join(ROOT, 'bench', 'figures', 'v2_2026-10-23', 'inputs', '00232213_repair.py')
    ns = {'__name__': '__main__'}
    src = '\n'.join(l for l in open(prog).read().splitlines() if 'exporters.export' not in l)
    exec(compile(src, prog, 'exec'), ns)
    res = ns.get('final_result', ns.get('result'))
    comp = str(tmp_path / 'compound.stl')
    cq.exporters.export(cq.Compound.makeCompound([v for v in res.vals() if isinstance(v, cq.Shape)]), comp,
                        tolerance=1e-3, angularTolerance=0.1)
    assert trimesh.load(comp, force='mesh').body_count == 1  # merged: body count says nothing
    out = str(tmp_path / 'union.stl')
    p = subprocess.run([sys.executable, os.path.join(ROOT, 'bench', 'union_replay.py'), prog, out],
                       capture_output=True, text=True, cwd=str(tmp_path))
    rec = json.loads(p.stdout.strip().splitlines()[-1])
    assert rec['built'] and rec['fused'] and rec['n_solids'] == 139
    u = trimesh.load(out, force='mesh')
    assert u.is_watertight and u.area < 0.7 * trimesh.load(comp, force='mesh').area

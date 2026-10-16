"""
CADFit's analysis stages as on-demand agent skills.

The `pool` toolset (cad_tools.py) hands the agent candidates that a full
`run_pipeline.py --keep-history` run precomputed. Here the agent starts with
nothing and runs the stages itself, one call at a time:

  detect_directions  Gauss-map extrusion directions beyond X/Y/Z (detect_directions.py)
  extract_sketch     slice the target at a plane, group loops into profiles with
                     holes (split_loops.py) and fit lines/arcs (fit_primitives.py)
  fit_extrude        sweep a sketch along its normal against the target surface
                     (analyze_loop_translation.py) and turn the matching extents
                     into extrusion candidates (greedy_search.py)
  fit_revolve        find symmetry axes of a sketch whose revolution matches the
                     target (analyze_revolve_axis.py) and build revolve candidates
  section_extrude    extrude the target's cross-section at a plane through its
                     full extent (section_extrude.py)

Every candidate a skill makes is built as a CadQuery script, executed, scored
against the target and added to the candidate list, where the agent uses it
through list_candidates / show_candidate / add_candidate as in the pool toolset.

Toolset `code` is the same workspace without these skills (and without
candidates): the agent can only read the target and write CadQuery itself.
"""
import contextlib
import functools
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cad_tools import ROOT, TOOL_SPECS, CadWorkspace, _r  # noqa: E402,F401  (ROOT: CADFit on sys.path)
import analyze_loop_translation as _alt  # noqa: E402
import analyze_revolve_axis as _ara  # noqa: E402
import cadquery_ops as _cqo  # noqa: E402
import detect_directions as _dd  # noqa: E402
import extract_sketches as _es  # noqa: E402
import fit_primitives as _fp  # noqa: E402
import greedy_search as _gs  # noqa: E402
import iou  # noqa: E402
import section_extrude as _se  # noqa: E402
import split_loops as _sl  # noqa: E402

# Stage settings of the fresh-cohort pipeline arms (bench/run_parallel_arms.sh):
# fast one-sided CD with at most 400 points a loop, translations in [-2, 2] by 0.01.
os.environ.setdefault('CADFIT_FAST_CD', '1')
os.environ.setdefault('CADFIT_TRANSLATION_MAXPTS', '400')
_T_RANGE, _T_STEP = (-2.0, 2.0), 0.01
_N_SURFACE = 100000
_gs.DENSIFY_REVOLVE_SPLIT = True  # see greedy_search.py: fixes revolve profiles split at the axis
# Revolve analysis as run_pipeline.py calls it: 0 and 90 degree trial rotations, CD threshold 0.01.
_ANGLES, _ANGLE_STEP, _REV_CD = (0.0, 90.0), 90.0, 0.01
_SEED = 0

_AXES = {'x': (1.0, 0.0, 0.0), 'y': (0.0, 1.0, 0.0), 'z': (0.0, 0.0, 1.0)}
_MIN_LOOP_AREA = 1e-6  # numerical slivers only (split_loops.py's 1e-3 drops real small features)
_MAX_SHOWN = 20         # sketches listed per extract_sketch reply (largest first)


def _unit(v):
    """A direction from a 3-vector or an axis name."""
    if isinstance(v, str) and v.lower().strip('+') in _AXES:
        v = _AXES[v.lower().strip('+')]
    v = np.asarray(v, dtype=float).reshape(-1)
    if v.shape != (3,) or not np.isfinite(v).all() or np.linalg.norm(v) < 1e-9:
        raise ValueError('normal must be a nonzero 3-vector such as [0, 0, 1] (or "x", "y", "z")')
    return v / np.linalg.norm(v)


def _primitive_counts(actions):
    n = {'lines': 0, 'arcs': 0, 'circles': 0, 'splines': 0}
    for a in actions:
        for key, word in (('lines', 'lineTo'), ('arcs', 'threePointArc'), ('circles', 'circle'),
                          ('splines', 'spline')):
            n[key] += a.count(word)
    return n


def _nest(loops3d, origin, normal, xdir):
    """Loops of one slice -> profiles [(loops, areas)] by even-odd nesting:
    a loop inside an even number of others is an outer boundary, one inside an
    odd number is a hole of its innermost container. So material islands inside
    holes become profiles of their own (split_loops.group_contained_loops would
    list them as holes of the outermost loop). Largest profile first."""
    polys = [_sl._loop_polygon(lp, origin, normal, xdir) for lp in loops3d]
    areas = [abs(p.area) if p is not None and not p.is_empty else 0.0 for p in polys]
    keep = [i for i, a in enumerate(areas) if a >= _MIN_LOOP_AREA]
    n_tiny = len(loops3d) - len(keep)
    pts = {i: polys[i].representative_point() for i in keep}
    contains = {i: [j for j in keep if j != i and areas[j] > areas[i] and polys[j].contains(pts[i])] for i in keep}
    profiles = {}
    for i in sorted(keep, key=lambda i: -areas[i]):
        depth = len(contains[i])
        if depth % 2 == 0:
            profiles[i] = [i]
        else:  # hole of the innermost (smallest) container at depth - 1
            parents = [j for j in contains[i] if len(contains[j]) == depth - 1]
            if parents:
                p = min(parents, key=lambda j: areas[j])
                profiles.setdefault(p, [p]).append(i)
    out = [([loops3d[k] for k in ks], [areas[k] for k in ks]) for ks in profiles.values()]
    return sorted(out, key=lambda g: -g[1][0]), n_tiny


def _quiet(fn):
    """The pipeline stages print progress; send it to <workdir>/skills.log."""
    @functools.wraps(fn)
    def run(self, *a, **k):
        with open(os.path.join(self.workdir, 'skills.log'), 'a') as log, contextlib.redirect_stdout(log):
            print(f'== {fn.__name__} {a} {k}')
            return fn(self, *a, **k)
    return run


class SkillWorkspace(CadWorkspace):
    """CadWorkspace whose candidates come from skills the agent calls."""

    def __init__(self, gt_stl, workdir):
        super().__init__(gt_stl, workdir)
        self.sketches = {}  # 'S<n>' -> sketch entry (split_loops schema) + fitted actions
        self._slices = {}   # rounded (normal, offset) -> first reply, so a repeated call is free and identical
        self._fits = {}     # (skill, sketch/axis key) -> candidate ids
        self._surf = None

    def _surface_points(self):
        if self._surf is None:
            self._surf = _alt.sample_surface_points(self.gt_mesh, _N_SURFACE, seed=_SEED)
        return self._surf

    def _register(self, script, stem, info):
        """Run a generated CadQuery script; add its solid as a scored candidate."""
        stl = os.path.join(self.workdir, f'{stem}.stl')
        py = os.path.join(self.workdir, f'{stem}.py')
        if not _cqo.execute_cadquery_script(script, stl, py) or not os.path.exists(stl):
            return None
        m = iou._cached_manifold(stl, False)
        if m is None or m.volume() <= 1e-9:
            return None
        vi, vc = (m ^ self.gt).volume(), m.volume()
        lo, hi = np.array(m.bounding_box()[:3]), np.array(m.bounding_box()[3:])
        cid = f'C{len(self.candidates)}'
        self.candidates[cid] = dict(info, iou=round(vi / (vc + self.gt_vol - vi), 4),
                                    precision=round(vi / vc, 4), coverage=round(vi / self.gt_vol, 4),
                                    vol_frac_of_target=round(vc / self.gt_vol, 4),
                                    bbox_min=_r(lo), bbox_max=_r(hi), _stl=stl, _py=py, _m=m)
        return cid

    def _public(self, cid):
        return dict(id=cid, **{k: v for k, v in self.candidates[cid].items() if not k.startswith('_')})

    def _sketch(self, sketch):
        e = self.sketches.get(sketch)
        if e is None:
            raise KeyError(f'unknown sketch {sketch!r}; extract_sketch returns ids like S0')
        return e

    @_quiet
    def detect_directions(self):
        """Sketch-plane normals: the extrusion directions detect_directions.py finds
        (walls parallel to them) and the normals of large flat faces.

        detect_directions.py skips flat-face normals because the pipeline slices
        flat faces in a separate stage (extract_planar_contours.py); an agent has
        only this skill, so both kinds are listed."""
        found = _dd.detect_directions(self.gt_mesh)
        flat = self.describe_target()['flat_face_directions']
        return {'axes': [list(v) for v in _AXES.values()],
                'other_directions': [{'direction': _r(d['direction']), 'wall_area_frac': d['support'],
                                      'n_walls': d['walls']} for d in found],
                'flat_face_normals': [{'normal': f['normal'], 'area_frac': f['area_frac'],
                                       'planes_at': f['planes_at']} for f in flat],
                'note': 'other_directions: off-axis directions with many faces parallel to them (walls an '
                        'extrusion along them would make). flat_face_normals: normals of the flat faces, with '
                        'the offsets of their planes. Any of these is a good extract_sketch normal.'}

    @_quiet
    def extract_sketch(self, normal, offset):
        """Slice the target, group loops into profiles with holes, fit lines/arcs."""
        n = _unit(normal)
        offset = float(offset)
        key = (tuple(np.round(n, 4)), round(offset, 4))
        if key in self._slices:  # the same reply as the first time (same cap and counts)
            return dict(self._slices[key], note='same plane as before')
        origin = n * offset
        _, loops3d = _es.slice_mesh_loops(self.gt_mesh, tuple(origin), tuple(n), samples_per_loop=3000)
        loops3d = [lp for lp in loops3d if len(lp) >= 3]
        if not loops3d:
            proj = (self.gt_mesh.vertices * n).sum(1)  # not `@`: Accelerate BLAS raises spurious FP warnings
            lo, hi = proj.min(), proj.max()
            self._slices[key] = {'sketches': [], 'note': f'the plane misses the target; along this normal the '
                                                         f'target spans offsets {lo:.3f} to {hi:.3f}'}
            return self._slices[key]
        xdir = _es.compute_xdir(tuple(n))
        o, nn = origin.tolist(), n.tolist()
        profiles, n_tiny = _nest(loops3d, o, nn, xdir)
        ids = []
        for group, areas in profiles:
            entry = {'origin': o, 'normal': nn, 'xdir': list(xdir), 'loops_3d': group, 'loop_areas': areas}
            actions = _fp.build_action_instances_from_entry(entry)
            if not actions:
                continue
            sid = f'S{len(self.sketches)}'
            self.sketches[sid] = dict(entry, actions=actions)
            ids.append(sid)
        out = {'plane': {'normal': _r(n), 'offset': round(offset, 4)},
               'sketches': [self._sketch_info(s) for s in ids[:_MAX_SHOWN]]}
        if len(ids) > _MAX_SHOWN:
            out['n_more_sketches'] = len(ids) - _MAX_SHOWN
            out['more_sketch_ids'] = f'{ids[_MAX_SHOWN]}..{ids[-1]} (smaller profiles)'
        if n_tiny:
            out['n_sliver_loops_dropped'] = n_tiny
        self._slices[key] = out
        return out

    def _sketch_info(self, sid):
        e = self.sketches[sid]
        pts = np.concatenate([np.asarray(lp, float) for lp in e['loops_3d']])
        areas = e['loop_areas']
        return {'id': sid, 'n_loops': len(areas), 'outer_area': round(areas[0], 4),
                'hole_areas': [round(a, 4) for a in areas[1:]],
                'bbox_min': _r(pts.min(0)), 'bbox_max': _r(pts.max(0)),
                'primitives': _primitive_counts(e['actions'])}

    @_quiet
    def fit_extrude(self, sketch):
        """analyze_loop_translation.py on one sketch -> extents -> extrusion candidates."""
        try:
            e = self._sketch(sketch)
        except KeyError as err:
            return {'error': str(err)}
        key = ('extrude', sketch)
        if key not in self._fits:
            idx = int(sketch[1:])
            folder = os.path.join(self.workdir, 'translation')
            os.makedirs(folder, exist_ok=True)
            mesh_data = {'vertices': self.gt_mesh.vertices, 'faces': self.gt_mesh.faces}
            entry = {k: v for k, v in e.items() if k != 'actions'}
            _alt.process_single_sketch((idx, entry, self._surface_points(), mesh_data, folder,
                                        _T_RANGE, _T_STEP, False))
            data = _gs.load_translation_analysis(folder, idx)
            ids = []
            for op in (_gs.create_extrusion_from_translation(entry, data, idx) if data else []):
                stem = f'sketch_{idx}_{op["source"]}'
                script = _cqo.generate_cadquery_script([op['actions']], op['height'],
                                                       os.path.join(self.workdir, stem + '.stl'))
                cid = self._register(script, stem, {'type': 'extrude', 'from_sketch': sketch,
                                                    'normal': _r(op['normal']), 'height': round(op['height'], 3),
                                                    'start_offset': round(float(np.dot(op['origin'], op['normal'])), 3)})
                if cid:
                    ids.append(cid)
            self._fits[key] = ids
        ids = self._fits[key]
        return {'sketch': sketch, 'candidates': [self._public(c) for c in ids],
                **({} if ids else {'note': 'no extent of this sketch matches the target surface'})}

    @_quiet
    def fit_revolve(self, sketch):
        """analyze_revolve_axis.py on one sketch -> symmetry axes -> revolve candidates."""
        try:
            e = self._sketch(sketch)
        except KeyError as err:
            return {'error': str(err)}
        key = ('revolve', sketch)
        if key not in self._fits:
            idx = int(sketch[1:])
            folder = os.path.join(self.workdir, 'revolve')
            os.makedirs(folder, exist_ok=True)
            mesh_data = {'vertices': self.gt_mesh.vertices, 'faces': self.gt_mesh.faces}
            entry = {k: v for k, v in e.items() if k != 'actions'}
            _ara.process_single_sketch((idx, entry, self._surface_points(), mesh_data, folder,
                                        _ANGLES, _ANGLE_STEP, False, _REV_CD))
            configs = _gs.load_revolve_analysis(folder, idx)
            ids = []
            for op in (_gs.create_revolve_from_analysis(entry, configs, idx) if configs else []):
                stem = f'sketch_{idx}_revolve_{op.get("axis_idx", len(ids))}'
                script = _cqo.generate_cadquery_revolve_script(
                    op['actions'], tuple(op['axis_start']), tuple(op['axis_end']), op['angle'],
                    os.path.join(self.workdir, stem + '.stl'), origin=op['origin'], normal=op['normal'],
                    xdir=op['xdir'])
                # axis_start/axis_end are in the sketch plane's local frame; report world coords.
                u, v, n = _fp.plane_basis(op['normal'], op['xdir'])
                B = np.stack([u, v, n], axis=1)
                p0 = np.asarray(op['origin'], float) + B @ np.asarray(op['axis_start'], float)
                d = B @ (np.asarray(op['axis_end'], float) - np.asarray(op['axis_start'], float))
                cid = self._register(script, stem, {'type': 'revolve', 'from_sketch': sketch,
                                                    'axis_point': _r(p0), 'axis_direction': _r(d / np.linalg.norm(d)),
                                                    'angle': op['angle']})
                if cid:
                    ids.append(cid)
            self._fits[key] = ids
        ids = self._fits[key]
        return {'sketch': sketch, 'candidates': [self._public(c) for c in ids],
                **({} if ids else {'note': 'no symmetry axis of this sketch revolves into the target'})}

    @_quiet
    def section_extrude(self, axis, offset=None):
        """section_extrude.py: the cross-section at axis=offset extruded through the part."""
        if axis not in ('x', 'y', 'z'):
            return {'error': "axis must be 'x', 'y' or 'z'"}
        k = 'xyz'.index(axis)
        lo, hi = self.gt_mesh.bounds[0][k], self.gt_mesh.bounds[1][k]
        value = 0.5 * (lo + hi) if offset is None else float(offset)
        key = ('section', axis, round(value, 4))
        if key not in self._fits:
            polys = _se.section_polygons(self.gt_mesh, k, value)
            ids = []
            if polys:
                n = 1000 + len(self._fits)
                stem = f'generic_{n}_section_{axis}'
                script = _cqo.generate_generic_script(_se.extrusion_code(polys, k, lo, hi),
                                                      os.path.join(self.workdir, stem + '.stl'), n)
                cid = self._register(script, stem, {'type': 'section_extrude', 'axis': axis,
                                                    'section_at': round(value, 3), 'n_profiles': len(polys)})
                if cid:
                    ids.append(cid)
            self._fits[key] = ids
        ids = self._fits[key]
        return {'candidates': [self._public(c) for c in ids],
                **({} if ids else {'note': f'no cross-section at {axis}={value:.3f}; the target spans '
                                           f'{lo:.3f} to {hi:.3f} along {axis}'})}


_VEC = {'type': 'array', 'items': {'type': 'number'}, 'minItems': 3, 'maxItems': 3}

SKILL_SPECS = [
    ('detect_directions', 'CADFit stage: the directions along which the target looks extruded (from the areas of its '
     'face normals), beyond the X/Y/Z axes. Use them as sketch-plane normals.', {}),
    ('extract_sketch', 'CADFit stage: slice the target with the plane perpendicular to `normal` at signed distance `offset` '
     'from the origin along it (normal is scaled to unit length), group the cut loops into profiles (outer '
     'boundary + holes; islands inside holes are profiles of their own) and fit lines and arcs to them. Returns one sketch id per profile '
     '(S0, S1, ...) with its area, size and fitted primitives. Feed the ids to fit_extrude / fit_revolve.',
     {'normal': _VEC, 'offset': {'type': 'number'}}),
    ('fit_extrude', 'CADFit stage: sweep a sketch along its normal, find the ranges where it matches the target '
     'surface and build an extrusion candidate for each. Candidates are scored against the target (iou, precision, '
     'coverage) and listed by list_candidates; add them with add_candidate.', {'sketch': {'type': 'string'}}),
    ('fit_revolve', 'CADFit stage: find symmetry axes of a sketch for which revolving its half-profile matches the '
     'target, and build a revolve candidate for each (scored like fit_extrude).', {'sketch': {'type': 'string'}}),
    ('section_extrude', "CADFit stage: take the target's cross-section in the plane axis=offset (default: middle) and "
     'extrude it through the full extent of the target along that axis. One scored candidate.',
     {'axis': {'type': 'string', 'enum': ['x', 'y', 'z']}, 'offset': {'type': 'number'}}),
]

_REQUIRED = {'show_candidate': ['id'], 'add_candidate': ['id'], 'add_code': ['code'], 'remove_step': ['step'],
             'section': ['axis', 'value'], 'extract_sketch': ['normal', 'offset'], 'fit_extrude': ['sketch'],
             'fit_revolve': ['sketch'], 'section_extrude': ['axis']}
_CANDIDATE_TOOLS = ('list_candidates', 'show_candidate', 'add_candidate')


def toolset_specs(toolset):
    """Tool specs for a toolset: pool (precomputed candidates), skills, code."""
    if toolset == 'pool':
        return list(TOOL_SPECS)
    base = [s for s in TOOL_SPECS if s[0] not in _CANDIDATE_TOOLS]
    if toolset == 'code':
        return base
    if toolset == 'skills':
        return base[:1] + SKILL_SPECS + [s for s in TOOL_SPECS if s[0] in _CANDIDATE_TOOLS] + base[1:]
    raise ValueError(f'unknown toolset {toolset}')


def openai_tools(toolset):
    return [{'type': 'function', 'function': {
        'name': n, 'description': d,
        'parameters': {'type': 'object', 'properties': p, 'required': _REQUIRED.get(n, [])}}}
        for n, d, p in toolset_specs(toolset)]

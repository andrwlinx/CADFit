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
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cad_tools import ROOT, TOOL_SPECS, CadWorkspace, _r  # noqa: E402,F401  (ROOT: CADFit on sys.path)
import detect_directions as _dd  # noqa: E402
import extract_sketches as _es  # noqa: E402
import fit_primitives as _fp  # noqa: E402
import split_loops as _sl  # noqa: E402

_AXES = {'x': (1.0, 0.0, 0.0), 'y': (0.0, 1.0, 0.0), 'z': (0.0, 0.0, 1.0)}
_MIN_LOOP_AREA = 1e-3  # split_loops.py drops smaller loops


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


class SkillWorkspace(CadWorkspace):
    """CadWorkspace whose candidates come from skills the agent calls."""

    def __init__(self, gt_stl, workdir):
        super().__init__(gt_stl, workdir)
        self.sketches = {}  # 'S<n>' -> sketch entry (split_loops schema) + fitted actions
        self._slices = {}   # rounded (normal, offset) -> sketch ids, so a repeated call is free

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

    def extract_sketch(self, normal, offset):
        """Slice the target, group loops into profiles with holes, fit lines/arcs."""
        n = _unit(normal)
        offset = float(offset)
        key = (tuple(np.round(n, 4)), round(offset, 4))
        if key in self._slices:
            return {'sketches': [self._sketch_info(s) for s in self._slices[key]], 'note': 'same plane as before'}
        origin = n * offset
        _, loops3d = _es.slice_mesh_loops(self.gt_mesh, tuple(origin), tuple(n), samples_per_loop=3000)
        loops3d = [lp for lp in loops3d if len(lp) >= 3]
        if not loops3d:
            self._slices[key] = []
            proj = (self.gt_mesh.vertices * n).sum(1)  # not `@`: Accelerate BLAS raises spurious FP warnings
            lo, hi = proj.min(), proj.max()
            return {'sketches': [], 'note': f'the plane misses the target; along this normal the target spans '
                                            f'offsets {lo:.3f} to {hi:.3f}'}
        xdir = _es.compute_xdir(tuple(n))
        o, nn = origin.tolist(), n.tolist()
        groups = _sl.group_contained_loops(loops3d, o, nn, xdir) if len(loops3d) > 1 else [loops3d]
        ids = []
        for group in groups:
            areas = [_sl.compute_loop_area(lp, o, nn, xdir) for lp in group]
            kept = [(lp, a) for lp, a in zip(group, areas) if a >= _MIN_LOOP_AREA]
            if not kept:
                continue
            entry = {'origin': o, 'normal': nn, 'xdir': list(xdir),
                     'loops_3d': [lp for lp, _ in kept], 'loop_areas': [a for _, a in kept]}
            actions = _fp.build_action_instances_from_entry(entry)
            if not actions:
                continue
            sid = f'S{len(self.sketches)}'
            self.sketches[sid] = dict(entry, actions=actions)
            ids.append(sid)
        self._slices[key] = ids
        return {'plane': {'normal': _r(n), 'offset': round(offset, 4)},
                'sketches': [self._sketch_info(s) for s in ids]}

    def _sketch_info(self, sid):
        e = self.sketches[sid]
        pts = np.concatenate([np.asarray(lp, float) for lp in e['loops_3d']])
        areas = e['loop_areas']
        return {'id': sid, 'n_loops': len(areas), 'outer_area': round(areas[0], 4),
                'hole_areas': [round(a, 4) for a in areas[1:]],
                'bbox_min': _r(pts.min(0)), 'bbox_max': _r(pts.max(0)),
                'primitives': _primitive_counts(e['actions'])}

    def fit_extrude(self, sketch):
        # PLACEHOLDER: real translation analysis lands at rung F2
        return {'candidates': [], 'note': 'PLACEHOLDER'}

    def fit_revolve(self, sketch):
        # PLACEHOLDER: real revolve analysis lands at rung F3
        return {'candidates': [], 'note': 'PLACEHOLDER'}

    def section_extrude(self, axis, offset=None):
        # PLACEHOLDER: real section extrusion lands at rung F3
        return {'candidates': [], 'note': 'PLACEHOLDER'}


_VEC = {'type': 'array', 'items': {'type': 'number'}, 'minItems': 3, 'maxItems': 3}

SKILL_SPECS = [
    ('detect_directions', 'CADFit stage: the directions along which the target looks extruded (from the areas of its '
     'face normals), beyond the X/Y/Z axes. Use them as sketch-plane normals.', {}),
    ('extract_sketch', 'CADFit stage: slice the target with the plane {p : dot(p, normal) = offset}, group the cut '
     'loops into profiles (outer boundary + holes) and fit lines and arcs to them. Returns one sketch id per profile '
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

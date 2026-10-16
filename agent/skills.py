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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cad_tools import TOOL_SPECS, CadWorkspace, _r  # noqa: E402


class SkillWorkspace(CadWorkspace):
    """CadWorkspace whose candidates come from skills the agent calls."""

    def __init__(self, gt_stl, workdir):
        super().__init__(gt_stl, workdir)
        self.sketches = {}  # 'S<n>' -> sketch entry (split_loops schema) + fitted actions

    def detect_directions(self):
        # PLACEHOLDER: fixed axis list; real Gauss-map detection lands at rung F1
        return {'directions': [{'direction': _r(d)} for d in ((1, 0, 0), (0, 1, 0), (0, 0, 1))],
                'note': 'PLACEHOLDER'}

    def extract_sketch(self, normal, offset):
        # PLACEHOLDER: no slicing yet; real extraction lands at rung F1
        return {'sketches': [], 'note': 'PLACEHOLDER'}

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

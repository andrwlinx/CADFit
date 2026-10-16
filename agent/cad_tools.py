"""
CADFit stages as tools for an LLM agent.

A CadWorkspace holds one target part and the model the agent is building.
The model is an ordered list of steps, each an `add` (union) or `cut`
(difference) of a solid that comes either from CADFit's candidate pool (the
extrude/revolve/loft candidates a `run_pipeline.py --keep-history` run left in
its part folder) or from CadQuery code the agent writes. Steps are combined
with exact manifold booleans, as `--exact-union` does, and scored against the
target with the same manifold IoU the pipeline uses.

Everything lives in CADFit's normalized frame: the target is centered and
scaled so its largest extent spans [-1, 1].

Agent-written code is untrusted. It runs in a fresh interpreter with
networking denied and file writes confined to the workspace directory: under
`sandbox-exec` on macOS, under `bwrap` (bubblewrap) on Linux, or under plain
user/mount/network namespaces (ns_sandbox.py) where bwrap cannot run.
"""
import glob
import json
import os
import re
import subprocess
import sys
import textwrap
import time

import numpy as np
import trimesh

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('CADFIT_EXACT_UNION', '1')  # multi-body candidate STLs: exact union of bodies
import iou  # noqa: E402

PY = sys.executable
_R = 3  # decimals in everything shown to the model


def _r(x, n=_R):
    return np.round(np.asarray(x, dtype=float), n).tolist()


def _sandboxed(workdir, argv):
    """argv wrapped so it runs without network and can write only to workdir."""
    w = os.path.realpath(workdir)
    if sys.platform == 'darwin':
        profile = ('(version 1)(allow default)(deny network*)(deny file-write*)'
                   f'(allow file-write* (subpath "{w}") (subpath "/private/var/folders") (literal "/dev/null"))')
        return ['sandbox-exec', '-p', profile, *argv]
    if _bwrap_works():
        # Read-only view of the host, private /tmp, writable workspace, own net namespace.
        return ['bwrap', '--ro-bind', '/', '/', '--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp',
                '--bind', w, w, '--unshare-net', '--die-with-parent', '--chdir', w, *argv]
    # Same guarantees from plain namespaces where bwrap cannot rebind the root
    # (ORCD GPU nodes inside Apptainer): see ns_sandbox.py.
    return ['unshare', '-rnm', PY, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ns_sandbox.py'),
            w, '--', *argv]


_BWRAP = None


def _bwrap_works():
    global _BWRAP
    if _BWRAP is None:
        try:
            _BWRAP = subprocess.run(['bwrap', '--ro-bind', '/', '/', '--dev', '/dev', '--proc', '/proc',
                                     '--unshare-net', 'true'], capture_output=True, timeout=30).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            _BWRAP = False
    return _BWRAP


def _strip_export(script):
    """A candidate script minus its export/print tail, leaving `result`."""
    keep = [ln for ln in script.splitlines()
            if not ln.strip().startswith(('cq.exporters.export', 'print('))]
    return '\n'.join(keep).strip() + '\n'


def _mesh_of(m):
    """manifold3d.Manifold -> trimesh."""
    g = m.to_mesh()
    return trimesh.Trimesh(np.asarray(g.vert_properties)[:, :3], np.asarray(g.tri_verts), process=False)


def _components(m, gt_vol, k=5):
    """Largest bodies of a residual manifold: volume share of the target, bbox, centroid."""
    out = []
    for b in m.decompose():
        v = b.volume()
        if v <= 1e-9:
            continue
        lo, hi = np.array(b.bounding_box()[:3]), np.array(b.bounding_box()[3:])
        out.append({'vol_frac_of_target': round(v / gt_vol, 4), 'bbox_min': _r(lo), 'bbox_max': _r(hi)})
    out.sort(key=lambda c: -c['vol_frac_of_target'])
    return out[:k]


class CadWorkspace:
    def __init__(self, gt_stl, workdir, candidate_dir=None, init_script=None):
        self.gt_stl = gt_stl
        self.workdir = os.path.realpath(workdir)
        os.makedirs(self.workdir, exist_ok=True)
        self.gt = iou._cached_manifold(gt_stl, True)
        if self.gt is None:
            raise RuntimeError(f'no manifold for target {gt_stl}')
        self.gt_vol = self.gt.volume()
        self.gt_mesh = iou.normalize_mesh(trimesh.load(gt_stl, force='mesh'))
        self.candidates = self._load_candidates(candidate_dir) if candidate_dir else {}
        self.steps = []        # [{'mode', 'source', 'code', 'm'}]
        self.n_code = 0
        self.history = []      # (time, iou, n_steps) after every model change
        self.best = (0.0, [])  # best IoU seen and the steps that gave it
        if init_script:
            # Start from a pipeline reconstruction: its STL is the solid (what the
            # judge scores), its script is kept for the CadQuery export.
            stl = init_script[:-3] + '.stl'
            m = iou._cached_manifold(stl, False)
            if m is None:
                raise RuntimeError(f'no manifold for {stl}')
            code = _strip_export(open(init_script).read())
            if re.search(r'^final_result\b', code, re.M):
                code += 'result = final_result\n'
            self.steps.append({'mode': 'add', 'source': 'pipeline', 'code': code, 'm': m})
            self._changed()

    # ---------- candidates ----------
    def _load_candidates(self, d):
        meta = {}
        ev = os.path.join(d, 'evaluated_operations.json')
        if os.path.exists(ev):
            for op in json.load(open(ev)):
                meta[os.path.basename(op.get('stl_path', ''))] = op
        cands = {}
        stls = sorted(glob.glob(os.path.join(d, 'sketch_*.stl')) + glob.glob(os.path.join(d, 'generic_*.stl')))
        for stl in stls:
            py = stl[:-4] + '.py'
            if not os.path.exists(py):
                continue
            m = iou._cached_manifold(stl, False)
            if m is None or m.volume() <= 1e-9:
                continue
            inter = m ^ self.gt
            vi, vc = inter.volume(), m.volume()
            op = meta.get(os.path.basename(stl), {})
            lo, hi = np.array(m.bounding_box()[:3]), np.array(m.bounding_box()[3:])
            c = {'type': op.get('type') or ('generic' if 'generic_' in stl else
                                            'revolve' if '_revolve_' in stl else 'extrude'),
                 'iou': round(vi / (vc + self.gt_vol - vi), 4),
                 'precision': round(vi / vc, 4),        # share of the candidate inside the target
                 'coverage': round(vi / self.gt_vol, 4),  # share of the target it covers
                 'vol_frac_of_target': round(vc / self.gt_vol, 4),
                 'bbox_min': _r(lo), 'bbox_max': _r(hi)}
            if c['type'] == 'extrude' and 'normal' in op:
                c.update(normal=_r(op['normal']), height=round(op['height'], _R))
            if c['type'] == 'revolve' and 'axis_start' in op:
                c.update(angle=op.get('angle'))
            cands[f'C{len(cands)}'] = dict(c, _stl=stl, _py=py, _m=m)
        return cands

    # ---------- model ----------
    def _model(self, steps=None):
        m = None
        for s in (self.steps if steps is None else steps):
            if s['mode'] == 'add':
                m = s['m'] if m is None else m + s['m']
            elif m is not None:
                m = m - s['m']
        return m

    def _score(self, m):
        if m is None or m.volume() <= 1e-12:
            return 0.0
        vi = (m ^ self.gt).volume()
        return vi / (m.volume() + self.gt_vol - vi)

    def _changed(self):
        s = self._score(self._model())
        self.history.append((time.time(), s, len(self.steps)))
        if s > self.best[0]:
            self.best = (s, list(self.steps))
        return s

    def _run_code(self, code, tag, timeout=90):
        stl = os.path.join(self.workdir, f'{tag}.stl')
        py = os.path.join(self.workdir, f'{tag}.py')
        script = ('import cadquery as cq\nimport math\n' + code +
                  f'\ncq.exporters.export(result, {stl!r})\n')
        with open(py, 'w') as f:
            f.write(script)
        if os.path.exists(stl):
            os.remove(stl)
        try:
            p = subprocess.run(_sandboxed(self.workdir, [PY, py]),
                               capture_output=True, text=True, timeout=timeout, cwd=self.workdir)
        except subprocess.TimeoutExpired:
            return None, f'timed out after {timeout}s'
        if p.returncode != 0 or not os.path.exists(stl):
            err = '\n'.join(ln for ln in p.stderr.splitlines() if 'Warning' not in ln)
            err = err.replace(self.workdir + os.sep, '')
            return None, err[-1500:] or f'exit {p.returncode}, nothing exported (is `result` a solid?)'
        mesh = trimesh.load(stl, force='mesh')
        if len(mesh.faces) == 0:
            return None, 'result is empty'
        m = iou._cached_manifold(stl, False)
        if m is None or m.volume() <= 1e-9:
            return None, 'result is not a closed solid with positive volume'
        return m, None

    def _add(self, code, mode, source):
        self.n_code += 1
        m, err = self._run_code(code, f'step{self.n_code}')
        if err:
            return {'error': err}
        before = self._score(self._model())
        self.steps.append({'mode': mode, 'source': source, 'code': code, 'm': m})
        after = self._changed()
        return {'step': len(self.steps) - 1, 'iou_before': round(before, 4), 'iou_after': round(after, 4)}

    # ---------- tools ----------
    def describe_target(self):
        """Size, volume and the dominant flat faces of the target."""
        m = self.gt_mesh
        lo, hi = m.bounds
        info = {'frame': 'normalized: largest extent spans [-1, 1], centered at the origin',
                'bbox_min': _r(lo), 'bbox_max': _r(hi), 'volume': round(self.gt_vol, 4),
                'bbox_fill': round(self.gt_vol / np.prod(hi - lo), 3),
                'surface_area': round(m.area, 3), 'n_faces': len(m.faces),
                'n_bodies': int(m.body_count), 'euler_number': int(m.euler_number)}
        # Flat faces (coplanar facets) grouped by direction, sign folded so a
        # plate's top and bottom share one entry; planes_at = offsets along it.
        groups = []
        for nrm, org, ar in zip(m.facets_normal, m.facets_origin, m.facets_area):
            for g in groups:
                d = float(np.dot(nrm, g['dir']))
                if abs(d) > 0.9998:
                    g['area'] += ar
                    off = round(float(np.dot(org, g['dir'])), _R)
                    g['lv'][off] = g['lv'].get(off, 0) + ar
                    break
            else:
                k = int(np.argmax(np.abs(nrm)))
                dir_ = nrm if nrm[k] > 0 else -nrm
                groups.append({'dir': dir_, 'area': ar, 'lv': {round(float(np.dot(org, dir_)), _R): ar}})
        # Tessellated curved walls are strips of tiny coplanar quads: count a
        # plane only if it holds 0.5% of the area, and a direction only at 1%.
        for g in groups:
            g['lv'] = {o: a for o, a in g['lv'].items() if a > 0.005 * m.area}
            g['area'] = sum(g['lv'].values())
        shown = [g for g in sorted(groups, key=lambda g: -g['area']) if g['area'] > 0.01 * m.area][:6]
        info['flat_face_directions'] = [
            {'normal': _r(g['dir']), 'area_frac': round(g['area'] / m.area, 3),
             'planes_at': sorted(float(o) for o, _ in sorted(g['lv'].items(), key=lambda kv: -kv[1])[:10])}
            for g in shown]
        info['curved_or_small_face_area_frac'] = round(1 - sum(g['area'] for g in shown) / m.area, 3)
        info['n_candidates'] = len(self.candidates)
        return info

    def list_candidates(self, sort_by='iou', type=None, offset=0, limit=15):
        """CADFit candidates with their fit to the target."""
        rows = [dict(id=k, **{kk: vv for kk, vv in c.items() if not kk.startswith('_')})
                for k, c in self.candidates.items() if type in (None, '', c['type'])]
        key = {'iou': lambda r: -r['iou'], 'coverage': lambda r: -r['coverage'],
               'precision': lambda r: -r['precision'], 'outside': lambda r: r['precision']}
        rows.sort(key=key.get(sort_by, key['iou']))
        return {'total': len(rows), 'candidates': rows[offset:offset + limit]}

    def show_candidate(self, id):
        c = self.candidates.get(id)
        if c is None:
            return {'error': f'unknown candidate {id}'}
        return {'id': id, 'code': _strip_export(open(c['_py']).read())}

    def add_candidate(self, id, mode='add'):
        c = self.candidates.get(id)
        if c is None:
            return {'error': f'unknown candidate {id}'}
        if mode not in ('add', 'cut'):
            return {'error': "mode must be 'add' or 'cut'"}
        before = self._score(self._model())
        self.steps.append({'mode': mode, 'source': id, 'code': _strip_export(open(c['_py']).read()),
                           'm': c['_m']})
        after = self._changed()
        return {'step': len(self.steps) - 1, 'iou_before': round(before, 4), 'iou_after': round(after, 4)}

    def add_code(self, code, mode='add'):
        if mode not in ('add', 'cut'):
            return {'error': "mode must be 'add' or 'cut'"}
        return self._add(code, mode, source='code')

    def remove_step(self, step):
        if not 0 <= step < len(self.steps):
            return {'error': f'no step {step}'}
        before = self._score(self._model())
        self.steps.pop(step)
        after = self._changed()
        return {'removed': step, 'iou_before': round(before, 4), 'iou_after': round(after, 4)}

    def list_steps(self):
        return {'steps': [{'step': i, 'mode': s['mode'], 'source': s['source'],
                           'vol_frac_of_target': round(s['m'].volume() / self.gt_vol, 4)}
                          for i, s in enumerate(self.steps)],
                'iou': round(self._score(self._model()), 4)}

    def evaluate(self):
        """IoU and where the model is wrong: missing and extra material."""
        m = self._model()
        if m is None:
            return {'iou': 0.0, 'note': 'model is empty'}
        miss, extra = self.gt - m, m - self.gt
        return {'iou': round(self._score(m), 4),
                'model_vol_frac_of_target': round(m.volume() / self.gt_vol, 4),
                'missing_frac': round(miss.volume() / self.gt_vol, 4),
                'extra_frac': round(extra.volume() / self.gt_vol, 4),
                'n_missing_regions': sum(b.volume() > 1e-9 for b in miss.decompose()),
                'n_extra_regions': sum(b.volume() > 1e-9 for b in extra.decompose()),
                'largest_missing_regions': _components(miss, self.gt_vol),
                'largest_extra_regions': _components(extra, self.gt_vol)}

    def section(self, axis, value, max_points=60):
        """Cross-sections of target and model by the plane axis=value."""
        k = 'xyz'.index(axis)
        normal = np.eye(3)[k]
        origin = normal * value
        others = [a for a in 'xyz' if a != axis]

        def polys(mesh):
            if mesh is None:
                return []
            s = mesh.section(plane_origin=origin, plane_normal=normal)
            if s is None:
                return []
            # Project by dropping the axis coordinate (keeps world coordinates).
            out = []
            for p in s.to_planar(to_2D=_drop_axis(k))[0].polygons_full:
                p = p.simplify(0.002)
                ext = np.asarray(p.exterior.coords)[:-1]
                step = max(1, len(ext) // max_points)
                out.append({'area': round(p.area, 4), 'outer': _r(ext[::step]),
                            'holes': [_r(np.asarray(h.coords)[:-1][::max(1, len(h.coords) // 24)])
                                      for h in p.interiors]})
            out.sort(key=lambda d: -d['area'])
            return out[:8]

        m = self._model()
        return {'plane': f'{axis}={value}', 'coords': f'({others[0]}, {others[1]})',
                'target': polys(self.gt_mesh), 'model': polys(_mesh_of(m) if m is not None else None)}

    # ---------- output ----------
    def export(self, out_dir, steps=None):
        """Write the model as STL (exact booleans) and as one CadQuery script."""
        steps = self.best[1] if steps is None else steps
        os.makedirs(out_dir, exist_ok=True)
        m = self._model(steps)
        stl = os.path.join(out_dir, 'agent_model.stl')
        if m is not None:
            _mesh_of(m).export(stl)
        parts = ['import cadquery as cq', 'import math', '']
        for i, s in enumerate(steps):
            parts += [f'def _step_{i}():  # {s["mode"]} {s["source"]}',
                      textwrap.indent(s['code'], '    ').rstrip(), '    return result', '']
        body = []
        for i, s in enumerate(steps):
            if i == 0 or body == []:
                body.append(f'model = _step_{i}()' if s['mode'] == 'add' else f'# cut _step_{i} skipped (empty model)')
                if s['mode'] != 'add':
                    body = []
                continue
            body.append(f'model = model.{"union" if s["mode"] == "add" else "cut"}(_step_{i}())')
        parts += body + ['result = model', "cq.exporters.export(result, 'agent_model_cq.stl')", '']
        with open(os.path.join(out_dir, 'agent_model.py'), 'w') as f:
            f.write('\n'.join(parts))
        return stl if m is not None else None


def _drop_axis(k):
    """4x4 transform for trimesh to_planar: world -> 2D keeping the other two axes."""
    keep = [i for i in range(3) if i != k]
    T = np.zeros((4, 4))
    T[0, keep[0]] = 1
    T[1, keep[1]] = 1
    T[2, k] = 1
    T[3, 3] = 1
    return T


TOOL_SPECS = [
    ('describe_target', 'Bounding box, volume and the axis-aligned flat faces of the target (normal direction, '
     'share of surface area, and the coordinates of the planes they lie in). Call this first.', {}),
    ('list_candidates', "List CADFit's precomputed candidate solids (extrusions/revolves fitted to sketches it "
     "sliced out of the target). iou = IoU of the candidate alone; precision = share of the candidate lying inside "
     "the target (near 1 = safe to add); coverage = share of the target it covers. sort_by='outside' lists the "
     "candidates mostly outside the target, i.e. cut tools for holes/pockets.",
     {'sort_by': {'type': 'string', 'enum': ['iou', 'coverage', 'precision', 'outside']},
      'type': {'type': 'string', 'enum': ['extrude', 'revolve', 'generic']},
      'offset': {'type': 'integer'}, 'limit': {'type': 'integer'}}),
    ('show_candidate', 'CadQuery code of a candidate (useful as a template for your own code).',
     {'id': {'type': 'string'}}),
    ('add_candidate', 'Append a candidate to the model as a union (add) or difference (cut). Returns IoU before/after.',
     {'id': {'type': 'string'}, 'mode': {'type': 'string', 'enum': ['add', 'cut']}}),
    ('add_code', 'Append a solid built by your own CadQuery code (cadquery imported as cq, math available). The '
     'code must assign the solid to a variable named `result`, in the normalized frame. Returns IoU before/after, '
     'or the error.',
     {'code': {'type': 'string'}, 'mode': {'type': 'string', 'enum': ['add', 'cut']}}),
    ('remove_step', 'Remove a step from the model by its index.', {'step': {'type': 'integer'}}),
    ('list_steps', 'The current model: its steps and IoU.', {}),
    ('evaluate', "IoU of the current model plus where it is wrong: the target's material the model misses and the "
     'model material outside the target, as fractions of target volume, with bounding boxes of the largest regions.',
     {}),
    ('section', 'Cross-section polygons of target and current model in the plane axis=value (outer boundary and '
     'holes, coordinates in the two remaining axes). Use to read exact sketch shapes and to see what differs.',
     {'axis': {'type': 'string', 'enum': ['x', 'y', 'z']}, 'value': {'type': 'number'}}),
    ('finish', 'Stop. The best model seen during the session is kept as the answer.', {}),
]


def openai_tools():
    req = {'show_candidate': ['id'], 'add_candidate': ['id'], 'add_code': ['code'],
           'remove_step': ['step'], 'section': ['axis', 'value']}
    return [{'type': 'function', 'function': {
        'name': n, 'description': d,
        'parameters': {'type': 'object', 'properties': p, 'required': req.get(n, [])}}}
        for n, d, p in TOOL_SPECS]

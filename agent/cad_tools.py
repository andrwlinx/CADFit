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
# Tools v2 (CADFIT_AGENT_EXEC=1): after every model change the assembled
# CadQuery program is executed (OCC booleans with fuzzy retries, exec_verify.py)
# and its build/validity status and executed IoU are returned with the reply;
# the answer is the best executed valid program, not the best mesh model.
EXEC = os.environ.get('CADFIT_AGENT_EXEC') == '1'
# Tools v3: one executed check (replay + judge) of a model change gets at most this many
# seconds (tools v2: replay up to 180 s, judge unbounded; single calls reached 30 min).
CHECK_CAP = float(os.environ.get('CADFIT_CHECK_CAP', '120'))
from exec_verify import HELPERS as _HELPERS  # noqa: E402


class SessionTimeout(BaseException):
    """Session deadline reached inside a tool. A BaseException so the generic
    `except Exception` handlers of the geometry stages (axis refinement, slice
    fallbacks) cannot swallow it and keep working past the deadline."""


def run_until(deadline, fn, *args, **kwargs):
    """fn(*args, **kwargs), interrupted by SIGALRM at `deadline` (epoch seconds).
    Returns (value, None), or (None, error message) once the deadline passes.
    The same rule bounds agent episodes and the scripted policy."""
    import signal
    left = deadline - time.time()
    if left <= 0:
        return None, 'session time limit reached'

    def _alarm(*_):
        raise SessionTimeout('session time limit reached during the tool call')
    old = signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, left)
    try:
        return fn(*args, **kwargs), None
    except SessionTimeout as e:
        return None, str(e)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


class CheckTimeout(Exception):
    pass


def check_until(cap, fn, *args, **kwargs):
    """fn(*args, **kwargs) limited to `cap` seconds, nested inside run_until: the
    session alarm, if armed, is restored afterwards with its remaining time (and
    fires at once if that ran out). Returns (value, None) or (None, error)."""
    import signal
    t0 = time.time()
    outer_left = signal.getitimer(signal.ITIMER_REAL)[0]  # 0.0 when no session alarm is armed
    outer = signal.getsignal(signal.SIGALRM)
    limit = cap if not outer_left else min(cap, outer_left)
    hit = []

    def _alarm(*_):
        hit.append(1)
        raise CheckTimeout()
    signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, max(limit, 1e-3))
    try:
        return fn(*args, **kwargs), None
    except CheckTimeout:
        return None, f'check did not finish in {limit:.0f}s'
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, outer)
        if outer_left:
            rest = outer_left - (time.time() - t0)
            if rest <= 0 and callable(outer):
                outer(signal.SIGALRM, None)  # the session deadline passed during the check
            signal.setitimer(signal.ITIMER_REAL, max(rest, 1e-3))


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
        self.best_exec = (-1.0, [], False)  # tools v2: best executed (iou, steps, valid)
        self._exec_cache = {}  # program text -> executed record
        self.n_exec = 0
        self.deadline = None   # set by the agent loop: tool subprocesses stop there
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
        if EXEC:
            r = self._exec()
            if r is not None and r.get('built') and r.get('checked', True):
                cur = self.best_exec
                better = ((r['valid'], r['iou']) > (cur[2], cur[0]))
                if better:
                    self.best_exec = (r['iou'], list(self.steps), r['valid'])
        return s

    def _time_left(self, cap):
        if self.deadline is None:
            return cap
        return max(1.0, min(cap, self.deadline - time.time()))

    # ---------- executed program (tools v2) ----------
    def program(self, steps=None, export_name=None):
        """The CadQuery program of a step list: one function per step, combined
        with exec_verify's _fuse/_cut (OCC booleans, fuzzy retries)."""
        steps = self.steps if steps is None else steps
        parts = ['import cadquery as cq', 'import math', _HELPERS]
        for i, s in enumerate(steps):
            parts += [f'def _step_{i}():  # {s["mode"]} {s["source"]}',
                      textwrap.indent(s['code'], '    ').rstrip(), '    return result', '']
        body, started = [], False
        for i, s in enumerate(steps):
            if not started:
                if s['mode'] == 'add':
                    body.append(f'model = _step_{i}()')
                    started = True
                else:
                    body.append(f'# cut _step_{i} skipped (empty model)')
                continue
            body.append(f'model = {"_fuse" if s["mode"] == "add" else "_cut"}(model, _step_{i}())')
        parts += body + ['result = model' if started else 'result = None']
        if export_name:
            parts.append(f"cq.exporters.export(result, {export_name!r})")
        return '\n'.join(parts) + '\n'

    def _exec(self, steps=None):
        """Execute the assembled program in the sandbox; judge it against the target."""
        steps = self.steps if steps is None else steps
        if not steps or not any(s['mode'] == 'add' for s in steps):
            return None
        # Keyed by the program text: it fully determines the executed result,
        # while step dicts' id()s are reused after remove_step (stale replies).
        key = self.program(steps)
        if key in self._exec_cache:
            return self._exec_cache[key]
        self.n_exec += 1
        tag = f'exec{self.n_exec}'
        py, stl = (os.path.join(self.workdir, f'{tag}.py'), os.path.join(self.workdir, f'{tag}.stl'))
        open(py, 'w').write(key)
        rec = {'built': False, 'valid': False, 'iou': 0.0, 'checked': True}
        argv = [PY, os.path.join(ROOT, 'bench', 'cad_replay.py'), py, stl]
        t0 = time.time()
        t = self._time_left(CHECK_CAP)
        try:
            p = subprocess.run(_sandboxed(self.workdir, argv), capture_output=True, text=True, timeout=t,
                               cwd=self.workdir)
            r = json.loads(p.stdout.strip().splitlines()[-1])
            rec.update(built=r['built'], valid=r['valid'], n_solids=r.get('n_solids'))
            if r.get('error'):
                rec['error'] = r['error'].replace(self.workdir + os.sep, '')[:400]
        except subprocess.TimeoutExpired:
            rec['error'] = f'program did not finish in {t:.0f}s'
        except (IndexError, json.JSONDecodeError, KeyError):
            rec['error'] = 'program crashed the CAD kernel'
        rec['_m'], rec['_stl'] = None, stl
        if rec['built'] and os.path.exists(stl):
            # The answer is chosen by the same judge that scores it (bench/score.py):
            # _cached_manifold may repair or alpha-wrap a tessellation, which is not the
            # geometry the judge sees. The manifold is kept only to draw model sections.
            sys.path.insert(0, os.path.join(ROOT, 'bench'))
            import score

            def judge():
                return float(score.robust_iou(self.gt_stl, stl)['iou']), iou._cached_manifold(stl, False)
            # One check (replay + judge) gets CHECK_CAP seconds. A check cut short leaves the
            # step in place but unchecked: it never becomes the delivered answer (the best
            # checked valid program does), and its program is not checked again.
            out, err = check_until(max(5.0, CHECK_CAP - (time.time() - t0)), judge)
            if err:
                rec.update(checked=False, error=err)
            else:
                rec['iou'], m = out
                if m is not None and m.volume() > 1e-12:
                    rec['_m'] = m
        self._exec_cache[key] = rec
        return rec

    def _exec_report(self):
        """What the program builds, for tool replies (tools v2)."""
        if not EXEC:
            return {}
        r = self._exec()
        if r is None:
            return {}
        out = {'program_builds': r['built'], 'program_valid': r['valid'],
               'program_iou': round(r['iou'], 4) if r.get('checked', True) else None}
        if r.get('error'):
            out['program_error'] = r['error']
        if r['built'] and not r.get('checked', True):
            out['note'] = ('the program builds, but its check did not finish in time; it stays in the model '
                           'unchecked and is not the delivered answer unless no checked valid program exists')
        elif r['built'] and not r['valid']:
            out['note'] = ('the CadQuery program builds an OCC-invalid solid; the answer kept is the best valid '
                           'program so far')
        elif not r['built']:
            out['note'] = 'the CadQuery program fails to build; the answer kept is the best valid program so far'
        b = self.best_exec
        out['best_valid_program_iou'] = round(b[0], 4) if b[2] else None
        return out

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
            timeout = self._time_left(timeout)
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
        return {'step': len(self.steps) - 1, 'iou_before': round(before, 4), 'iou_after': round(after, 4),
                **self._exec_report()}

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
        return {'step': len(self.steps) - 1, 'iou_before': round(before, 4), 'iou_after': round(after, 4),
                **self._exec_report()}

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
        return {'removed': step, 'iou_before': round(before, 4), 'iou_after': round(after, 4),
                **self._exec_report()}

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
        rep = {}
        if EXEC:  # regions of what the program builds, when it builds a clean volume
            r = self._exec()
            rep = self._exec_report()
            if r is not None and r.get('_m') is not None:
                m = r['_m']
                rep['regions_from'] = 'executed program'
        miss, extra = self.gt - m, m - self.gt
        return {**rep, 'iou': round(self._score(m), 4),
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

        m, source = self._model(), 'mesh composition of the steps'
        if EXEC:  # tools v2: show what the program builds, the geometry evaluate() reports
            r = self._exec()
            if r is not None and r.get('_m') is not None:
                m, source = r['_m'], 'executed program'
        return {'plane': f'{axis}={value}', 'coords': f'({others[0]}, {others[1]})',
                'target': polys(self.gt_mesh), 'model': polys(_mesh_of(m) if m is not None else None),
                'model_source': source}

    # ---------- output ----------
    def answer_steps(self):
        """The steps of the delivered answer: under tools v2 the best executed
        program (valid first), otherwise the best mesh-scored model."""
        if EXEC and self.best_exec[0] >= 0:
            return self.best_exec[1]
        return self.best[1]

    def export(self, out_dir, steps=None):
        """Write the model as STL (exact booleans) and as one CadQuery script."""
        if EXEC and steps is None:
            # tools v2: the answer is the best executed program (valid first), and
            # the STL is what that program builds.
            steps = self.answer_steps()
            os.makedirs(out_dir, exist_ok=True)
            open(os.path.join(out_dir, 'agent_model.py'), 'w').write(
                self.program(steps, export_name='agent_model_cq.stl'))
            r = self._exec(steps) if steps else None
            stl = os.path.join(out_dir, 'agent_model.stl')
            if r is not None and r.get('built') and os.path.exists(r['_stl']):
                import shutil
                shutil.copy2(r['_stl'], stl)
                return stl
            m = self._model(steps)
            if m is not None:
                _mesh_of(m).export(stl)
                return stl
            return None
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

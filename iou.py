"""CPU mesh-boolean IoU.

Computes IoU(A, B) = volume(A ∩ B) / volume(A ∪ B) using manifold3d directly.
Replaces the prior GPU ray-cast sampler.

Mesh manifoldification is done via pymeshlab's `generate_alpha_wrap`, which
emits a guaranteed-watertight surface around any input (non-manifold, multiple
disconnected solids, micro-gaps, dense tessellation, etc.). This is much more
robust than the previous trimesh-based heal + manifold3d cleanup chain.
"""
import os
import numpy as np
import trimesh
import manifold3d


_OP_INTERSECT = manifold3d.OpType.Intersect
_OP_ADD = manifold3d.OpType.Add

# Alpha-wrap parameters (percentages of the mesh bounding-box diagonal).
# alpha: largest feature size that gets smoothed over (smaller = tighter).
# offset: how far outside the input surface the wrap can sit.
ALPHA_WRAP_ALPHA_PCT = 1.0
ALPHA_WRAP_OFFSET_PCT = 0.1

# Decimation target — alpha-wrap on multi-hundred-thousand-face meshes
# dominates per-STL runtime, so we cheaply decimate first.
_DECIMATE_FACE_THRESHOLD = 50_000


def normalize_mesh(mesh, box_min: float = -1.0, box_max: float = 1.0):
    """Center and uniformly scale `mesh` so its largest extent fits [box_min, box_max]."""
    bb_min = mesh.bounds[0]
    bb_max = mesh.bounds[1]
    center = 0.5 * (bb_min + bb_max)
    max_dim = float((bb_max - bb_min).max())
    if max_dim > 0:
        scale = (box_max - box_min) / max_dim
        mesh.apply_translation(-center)
        mesh.apply_scale(scale)
    return mesh


def _alpha_wrap(mesh, target_faces: int = _DECIMATE_FACE_THRESHOLD):
    """Return a guaranteed-watertight trimesh produced by pymeshlab's
    alpha-wrap filter. Decimates the input to `target_faces` first when it
    has more (cheap pass that drastically speeds up alpha-wrap on dense
    CAD STLs without changing the wrap's geometric output meaningfully).
    Falls back to the original mesh on any failure.

    pymeshlab's alpha-wrap can segfault on some meshes, which kills the whole
    pipeline process (stock crashed on a CADBench part in the final IoU
    check). Unless CADFIT_SAFE_WRAP=0, the wrap runs in a helper process and a
    crash there becomes the same soft failure as an exception."""
    if os.environ.get("CADFIT_SAFE_WRAP", "1") != "0":
        return _alpha_wrap_forked(mesh, target_faces)
    return _alpha_wrap_inproc(mesh, target_faces)


_WRAP_CLIENT = None


def _alpha_wrap_forked(mesh, target_faces):
    """Alpha-wrap in a persistent helper interpreter (cq_worker.py protocol).
    macOS forbids plain fork() once the Objective-C runtime is up, so this
    uses a long-lived subprocess instead; a segfault there only costs a
    restart and returns the input mesh (the usual soft failure)."""
    global _WRAP_CLIENT
    import tempfile
    import cq_worker
    if _WRAP_CLIENT is None:
        _WRAP_CLIENT = cq_worker._Client()
    fd, src = tempfile.mkstemp(suffix='.npz')
    os.close(fd)
    dst = src[:-4] + '_out.npz'
    try:
        np.savez(src, v=np.asarray(mesh.vertices, dtype=np.float64), f=np.asarray(mesh.faces, dtype=np.int64))
        script = (
            "import numpy as np, trimesh, iou\n"
            f"d = np.load({src!r})\n"
            "m = trimesh.Trimesh(vertices=d['v'], faces=d['f'], process=False)\n"
            f"w = iou._alpha_wrap_inproc(m, {int(target_faces)})\n"
            "assert w is not m, 'wrap failed'\n"
            f"np.savez({dst!r}, v=np.asarray(w.vertices), f=np.asarray(w.faces))\n")
        try:
            ok, _ = _WRAP_CLIENT.run(script, timeout=600)
        except Exception:
            ok = False
        if ok and os.path.exists(dst):
            d = np.load(dst)
            return trimesh.Trimesh(vertices=d['v'], faces=d['f'], process=True)
        return mesh
    finally:
        for p in (src, dst):
            try:
                os.unlink(p)
            except OSError:
                pass


def _alpha_wrap_inproc(mesh, target_faces):
    try:
        import pymeshlab
    except ImportError:
        return mesh
    try:
        ms = pymeshlab.MeshSet()
        ms.add_mesh(pymeshlab.Mesh(
            vertex_matrix=np.asarray(mesh.vertices, dtype=np.float64),
            face_matrix=np.asarray(mesh.faces, dtype=np.int32),
        ))
        if len(mesh.faces) > target_faces:
            try:
                ms.meshing_decimation_quadric_edge_collapse(
                    targetfacenum=target_faces,
                    preservenormal=True,
                    preserveboundary=True,
                )
            except Exception:
                pass
        ms.generate_alpha_wrap(
            alpha=pymeshlab.PercentageValue(ALPHA_WRAP_ALPHA_PCT),
            offset=pymeshlab.PercentageValue(ALPHA_WRAP_OFFSET_PCT),
        )
        out = ms.current_mesh()
        return trimesh.Trimesh(vertices=out.vertex_matrix(),
                                faces=out.face_matrix(),
                                process=True)
    except Exception as e:
        # Soft failure: caller can still try to build a manifold from the original.
        return mesh


def _to_manifold(mesh):
    """Build a manifold3d.Manifold from a trimesh mesh. Returns None on
    failure or empty result (volume == 0)."""
    verts = np.asarray(mesh.vertices, dtype=np.float32)
    faces = np.asarray(mesh.faces, dtype=np.uint32)
    try:
        mm = manifold3d.Mesh(vert_properties=verts, tri_verts=faces)
        m = manifold3d.Manifold(mm)
    except Exception:
        return None
    if m.volume() == 0.0:
        return None
    return m


def _manifold_boolean(a, b, op):
    """Run a manifold boolean and return the result Manifold, or None on failure."""
    try:
        return manifold3d.Manifold.batch_boolean([a, b], op)
    except AttributeError:
        # Older manifold3d API.
        if op is _OP_INTERSECT:
            return a & b
        if op is _OP_ADD:
            return a + b
    except Exception:
        return None
    return None


# LRU (dict insertion order + move-to-end on hit). Stock used an 8-entry FIFO,
# which evicted the ground truth every few candidate evaluations and re-ran its
# alpha-wrap (seconds each) hundreds of times per pruning pass.
_MANIFOLD_CACHE: dict = {}
_CACHE_MAX = 512  # candidate manifolds are small; exact-union reuses them every step


def _cache_get(key):
    if key in _MANIFOLD_CACHE:
        _MANIFOLD_CACHE[key] = _MANIFOLD_CACHE.pop(key)
        return True, _MANIFOLD_CACHE[key]
    return False, None


def _cache_put(key, value):
    if len(_MANIFOLD_CACHE) >= _CACHE_MAX:
        _MANIFOLD_CACHE.pop(next(iter(_MANIFOLD_CACHE)))
    _MANIFOLD_CACHE[key] = value

# CADFit++ correctness fix (opt-in via env so pool workers inherit it): only
# trust the direct manifold3d conversion when the mesh is a genuine volume.
# Stock's volume-ratio gate below compares the same divergence integral to
# itself and passes self-overlapping compounds (two extrusions sharing a face
# merge into one "body" on load), which then yield IoU > 1 and steer greedy
# search toward duplicate operations.
def _validate_enabled() -> bool:
    return os.environ.get("CADFIT_IOU_VALIDATE", "") not in ("", "0")


def _is_clean_volume(mesh) -> bool:
    try:
        return bool(mesh.is_watertight and mesh.is_winding_consistent and mesh.volume > 0)
    except Exception:
        return False


def _merged_manifold(mesh, rel_tol=0.01):
    """manifold3d straight from an STL whose indexing was lost on export
    (float32 rounding makes trimesh see cracks). Mesh.merge() re-stitches
    near-duplicate vertices; accept only a clean status and a volume that
    matches the mesh's own signed volume."""
    try:
        mm = manifold3d.Mesh(vert_properties=np.asarray(mesh.vertices, dtype=np.float32),
                             tri_verts=np.asarray(mesh.faces, dtype=np.uint32))
        mm.merge()
        m = manifold3d.Manifold(mm)
        if str(m.status()).endswith('NoError') and m.volume() > 0:
            v = abs(mesh.volume)
            if v > 0 and abs(m.volume() - v) <= rel_tol * v:
                return m
    except Exception:
        return None
    return None


def _bodies_union_manifold(mesh):
    """Exact manifold of a multi-body mesh: each closed body is converted on its
    own and the bodies are unioned by manifold3d, which resolves overlaps
    correctly. (Stock converted the whole compound at once, where overlapping
    shells break the volume math, and fell back to alpha-wrap.) Returns None if
    any body is open or fails to convert."""
    try:
        bodies = mesh.split(only_watertight=False)
        if not bodies or not all(b.is_watertight and b.is_winding_consistent for b in bodies):
            return None
        parts = [_to_manifold(b) for b in bodies]
        if any(p is None for p in parts):
            return None
        return manifold3d.Manifold.batch_boolean(parts, _OP_ADD) if len(parts) > 1 else parts[0]
    except Exception:
        return None


def _cached_manifold(path: str, normalize: bool):
    """Manifoldify the mesh at `path`, caching by `(path, mtime, normalize)`.

    Tries the direct conversion first (fast, no geometric distortion).
    Only falls back to alpha-wrap when the mesh is non-manifold / non-volume
    and manifold3d returns an empty manifold. Greedy search calls IoU
    hundreds of times against the same ground-truth file, so caching the
    result avoids re-running the (slow) alpha-wrap per call.
    """
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None
    key = (path, mtime, normalize)
    hit, cached = _cache_get(key)
    if hit:
        return cached
    try:
        mesh = trimesh.load(path, force='mesh')
    except Exception:
        _cache_put(key, None)
        return None
    if normalize:
        mesh = normalize_mesh(mesh)

    # Multi-body meshes (Compound STLs from CadQuery `.add()`) pass
    # `is_watertight` and `is_volume` but contain disjoint shells whose
    # pairwise overlapping regions break manifold3d's volume math
    # (gives vol(A∩B) > vol(A∪B)). Alpha-wrap merges them.
    try:
        multi_body = mesh.body_count > 1
    except Exception:
        multi_body = False

    # Try the direct manifold3d conversion first — even on non-watertight
    # inputs it often produces the right volume when vertex-merging closes
    # the topology. Compare against trimesh's signed-integral volume to
    # detect cases where it silently went wrong (the alpha-wrap pathway
    # used to produce ~50% under-volumes on slabs with holes).
    m = None
    if multi_body and os.environ.get("CADFIT_EXACT_UNION", "") not in ("", "0"):
        # Multi-body meshes (exact-union outputs, cuts that split a part, or
        # compounds of closed solids): union the bodies exactly.
        m = _bodies_union_manifold(mesh)
        if m is None:
            m = _merged_manifold(mesh)
    if m is None and not multi_body and not (_validate_enabled() and not _is_clean_volume(mesh)):
        m_direct = _to_manifold(mesh)
        if m_direct is not None:
            try:
                raw_vol = abs(mesh.volume)
                if raw_vol > 0:
                    ratio = m_direct.volume() / raw_vol
                    if 0.9 <= ratio <= 1.1:
                        m = m_direct
            except Exception:
                pass

    # Fall back to alpha-wrap if direct didn't yield a volume-consistent
    # manifold, or for multi-body meshes.
    if m is None:
        m = _to_manifold(_alpha_wrap(mesh))
        if m is None:
            m = _to_manifold(mesh)

    _cache_put(key, m)
    return m


def _wrapped_manifold(path: str, normalize: bool):
    """Alpha-wrapped manifold, bypassing the direct path (validation fallback)."""
    key = (path, 'wrapped', normalize)
    hit, cached = _cache_get(key)
    if hit:
        return cached
    try:
        mesh = trimesh.load(path, force='mesh')
        if normalize:
            mesh = normalize_mesh(mesh)
        m = _to_manifold(_alpha_wrap(mesh))
    except Exception:
        m = None
    _cache_put(key, m)
    return m


def _boolean_volumes(ma, mb):
    inter = _manifold_boolean(ma, mb, _OP_INTERSECT)
    uni = _manifold_boolean(ma, mb, _OP_ADD)
    if inter is None or uni is None:
        return None
    return abs(inter.volume()), abs(uni.volume())


def _volumes_consistent(ma, mb, v_inter, v_uni, tol=1e-4) -> bool:
    """inter <= min(|A|,|B|) and union >= max(|A|,|B|), up to a relative tolerance."""
    va, vb = abs(ma.volume()), abs(mb.volume())
    scale = max(va, vb, 1e-12)
    return v_inter <= min(va, vb) + tol * scale and v_uni >= max(va, vb) - tol * scale


def mesh_iou_cpu_boolean(mesh_path_a: str,
                         mesh_path_b: str,
                         normalize: bool = False,
                         verbose: bool = False) -> float:
    """IoU between two meshes via CPU booleans.

    Each input mesh is run through pymeshlab's alpha-wrap so it becomes a
    guaranteed-watertight manifold before manifold3d's boolean engine touches
    it. An LRU-ish cache keyed on (path, mtime, normalize) so the same
    ground-truth file isn't re-wrapped for every candidate during greedy search.
    `normalize=True` rescales mesh A to a [-1, 1] cube. Returns 0.0 on any
    failure or empty union.
    """
    ma = _cached_manifold(mesh_path_a, normalize)
    mb = _cached_manifold(mesh_path_b, normalize=False)
    if ma is None or mb is None:
        if verbose:
            print("[IOU] manifold construction failed")
        return 0.0

    vols = _boolean_volumes(ma, mb)
    if vols is None:
        if verbose:
            print("[IOU] boolean failed")
        return 0.0
    v_inter, v_uni = vols

    if _validate_enabled() and not _volumes_consistent(ma, mb, v_inter, v_uni):
        # The boolean engine was handed a non-volume. Re-run on alpha-wrapped
        # inputs; if that is still inconsistent, refuse to score it.
        ma2 = _wrapped_manifold(mesh_path_a, normalize)
        mb2 = _wrapped_manifold(mesh_path_b, normalize=False)
        vols = _boolean_volumes(ma2, mb2) if ma2 is not None and mb2 is not None else None
        if vols is None or not _volumes_consistent(ma2, mb2, *vols):
            print(f"[IOU] inconsistent boolean volumes for {os.path.basename(mesh_path_b)}; scoring 0")
            return 0.0
        v_inter, v_uni = vols
    if v_uni <= 0:
        return 0.0
    iou = v_inter / v_uni
    if verbose:
        print(f"[IOU] inter={v_inter:.6f} uni={v_uni:.6f} IoU={iou:.6f}")
    return iou

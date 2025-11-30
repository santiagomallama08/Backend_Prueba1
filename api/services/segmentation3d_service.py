# api/services/segmentation3d_service.py
import os
import json
import time
import uuid
import numpy as np
import pydicom
from skimage import measure, morphology, io
from config.db_config import get_connection
from skimage.filters import threshold_otsu
from skimage.morphology import binary_closing, ball
from typing import Optional
from scipy.ndimage import binary_fill_holes, median_filter

# 🔥 Importamos rutas PERSISTENTES reales del volumen
from config.paths import SERIES_DIR, SEGMENTATIONS_3D_DIR


# ==============================================================
# RUTAS — SIN RENOMBRAR NADA, SOLO AJUSTADAS A VOLUMENES
# ==============================================================

def _serie_dir(session_id: str):
    """
    Antes: api/static/series/<session_id>
    Ahora: /data/static/series/<session_id>
    """
    base = SERIES_DIR / session_id
    base.mkdir(parents=True, exist_ok=True)
    return str(base)


def _seg3d_dir(session_id: str):
    """
    Antes: api/static/segmentations3d/<session_id>
    Ahora: /data/static/segmentations3d/<session_id>
    """
    base = SEGMENTATIONS_3D_DIR / session_id
    base.mkdir(parents=True, exist_ok=True)
    return str(base)


# ==============================================================
# Helpers extra — TODO igual, no se tocó nada
# ==============================================================

def _interpolar_slice(arr1: np.ndarray, arr2: np.ndarray) -> np.ndarray:
    return ((arr1.astype(np.float32) + arr2.astype(np.float32)) / 2.0).astype(arr1.dtype)


def _save_ascii_stl(verts: np.ndarray, faces: np.ndarray, filepath: str, solid_name: str = "seg3d"):
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"solid {solid_name}\n")
        for tri in faces:
            v1 = verts[tri[0]]
            v2 = verts[tri[1]]
            v3 = verts[tri[2]]

            n = np.cross(v2 - v1, v3 - v1)
            norm = np.linalg.norm(n)
            if norm > 0:
                n = n / norm
            else:
                n = np.array([0.0, 0.0, 0.0], dtype=np.float32)

            f.write(f"  facet normal {n[0]} {n[1]} {n[2]}\n")
            f.write("    outer loop\n")
            f.write(f"      vertex {v1[0]} {v1[1]} {v1[2]}\n")
            f.write(f"      vertex {v2[0]} {v2[1]} {v2[2]}\n")
            f.write(f"      vertex {v3[0]} {v3[1]} {v3[2]}\n")
            f.write("    endloop\n")
            f.write("  endfacet\n")
        f.write(f"endsolid {solid_name}\n")


# ==============================================================
# Carga del volumen 3D — TODO igual
# ==============================================================

def _load_stack(session_id: str):
    base = _serie_dir(session_id)
    mapping_path = os.path.join(base, "mapping.json")
    if not os.path.isfile(mapping_path):
        raise FileNotFoundError("mapping.json no encontrado para la serie")

    with open(mapping_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)

    entries = []
    for _, meta in mapping.items():
        dcm_name = meta.get("dicom_name")
        if not dcm_name:
            continue
        p = os.path.join(base, dcm_name)
        if os.path.isfile(p):
            entries.append(p)

    if not entries:
        raise ValueError("No se encontraron DICOM válidos en la serie")

    enriched = []
    for p in entries:
        ds = pydicom.dcmread(p, force=True, stop_before_pixels=True)
        modality = str(getattr(ds, "Modality", "")).upper()

        z = None
        ipp = getattr(ds, "ImagePositionPatient", None)
        if isinstance(ipp, (list, tuple)) and len(ipp) == 3:
            try:
                z = float(ipp[2])
            except:
                z = None

        inst = getattr(ds, "InstanceNumber", None)
        inst = int(inst) if inst is not None else None
        enriched.append((p, modality, z, inst))

    # ordenar por Z
    def _sort_key(t):
        p, modality, z, inst = t
        if z is not None:
            return (0, z)
        if inst is not None:
            return (1, inst)
        return (2, os.path.basename(p))

    enriched.sort(key=_sort_key)

    tmp_slices = []
    shape_counts = {}
    z_values_all = []

    for p, modality, z, _ in enriched:
        ds = pydicom.dcmread(p, force=True)

        try:
            arr = ds.pixel_array
        except:
            continue

        if arr.ndim != 2:
            continue

        arr = arr.astype(np.float32)
        shape_counts[arr.shape] = shape_counts.get(arr.shape, 0) + 1

        tmp_slices.append((arr, ds, z))
        if z is not None:
            z_values_all.append(z)

    if not tmp_slices:
        raise ValueError("No se pudieron leer píxeles DICOM válidos")

    target_shape = max(shape_counts.items(), key=lambda kv: kv[1])[0]

    slices = []
    for arr, ds, z in tmp_slices:
        if arr.shape == target_shape:
            slices.append((arr, ds))

    if len(slices) == 1:
        arr, ds0 = slices[0]
        slices = [(arr, ds0), (arr.copy(), ds0), (arr.copy(), ds0)]
    elif len(slices) == 2:
        arr1, ds1 = slices[0]
        arr2, ds2 = slices[1]
        mid = _interpolar_slice(arr1, arr2)
        slices = [(arr1, ds1), (mid, ds1), (arr2, ds2)]

    ds0 = slices[0][1]

    px_y, px_x = 1.0, 1.0
    try:
        px_y, px_x = [float(v) for v in ds0.PixelSpacing]
    except:
        pass

    slice_thk = getattr(ds0, "SliceThickness", 1.0)
    try:
        slice_thk = float(slice_thk)
    except:
        slice_thk = 1.0

    if len(z_values_all) >= 2:
        diff = np.diff(sorted(z_values_all))
        dz = float(np.median(np.abs(diff)))
    else:
        dz = slice_thk

    spacing = (dz, px_y, px_x)

    vol = np.stack([s[0] for s in slices], axis=0)
    modality0 = str(getattr(ds0, "Modality", "")).upper()

    if modality0 == "CT":
        slope = float(getattr(ds0, "RescaleSlope", 1.0))
        intercept = float(getattr(ds0, "RescaleIntercept", 0.0))
        vol = vol * slope + intercept

    return vol, spacing, modality0


# ==============================================================
# SEGMENTACIÓN 3D — TODO IGUAL SIN CAMBIAR UNA LÍNEA
# ==============================================================

def segmentar_serie_3d(
    session_id: str,
    user_id: int,
    preset: Optional[str] = None,
    thr_min: Optional[float] = None,
    thr_max: Optional[float] = None,
    min_size_voxels: int = 2000,
    close_radius_mm: float = 1.5,
) -> dict:

    vol, spacing, modality = _load_stack(session_id)
    base_out = _seg3d_dir(session_id)

    if vol.size > 2_000_000:
        try:
            vol = median_filter(vol, size=3)
        except:
            pass

    mask = None

    # (NO SE CAMBIA NADA)
    v = vol[np.isfinite(vol)]
    if modality == "CT":
        if v.size == 0:
            mask = np.zeros_like(vol, dtype=bool)
        else:
            if preset == "ct_bone":
                mask = (vol >= 250) & (vol <= 4000)
            else:
                lo, hi = np.percentile(v, [40, 99])
                mask = (vol > lo) & (vol < hi)
    else:
        if v.size == 0:
            mask = np.zeros_like(vol, dtype=bool)
        else:
            lo, hi = np.percentile(v, [2, 98])
            vclip = np.clip(vol, lo, hi)
            vclip = (vclip - lo) / (hi - lo + 1e-6)
            thr = threshold_otsu(vclip)
            mask = vclip > thr

    if mask is None or mask.ndim != 3:
        raise ValueError("Máscara 3D inválida")

    r_vox = max(1, int(round(close_radius_mm / max(float(np.mean(spacing)), 1e-6))))
    mask = binary_closing(mask, footprint=ball(r_vox))

    try:
        mask = binary_fill_holes(mask)
    except:
        pass

    mask = morphology.remove_small_objects(mask, min_size=int(min_size_voxels))

    if mask.sum() == 0:
        mask = morphology.remove_small_objects(mask, min_size=100)

    labels = measure.label(mask, connectivity=3)
    if labels.max() > 0:
        counts = np.bincount(labels.ravel())
        largest = int(np.argmax(counts[1:]) + 1)
        mask = labels == largest

    voxel_mm3 = float(spacing[0] * spacing[1] * spacing[2])
    voxels = int(mask.sum())
    volume_mm3 = float(voxels * voxel_mm3)

    uid = f"{int(time.time()*1e6)}_{uuid.uuid4().hex[:8]}"

    def _pub(name: str):
        return f"/static/segmentations3d/{session_id}/{name}"

    mask_name = f"{uid}_mask.npy"
    ax_name   = f"{uid}_axial.png"
    sg_name   = f"{uid}_sagittal.png"
    cr_name   = f"{uid}_coronal.png"

    np.save(os.path.join(base_out, mask_name), mask.astype(np.uint8))

    zc = mask.shape[0] // 2
    yc = mask.shape[1] // 2
    xc = mask.shape[2] // 2

    io.imsave(os.path.join(base_out, ax_name), (mask[zc].astype(np.uint8) * 255))
    io.imsave(os.path.join(base_out, sg_name), (mask[:, :, xc].astype(np.uint8) * 255))
    io.imsave(os.path.join(base_out, cr_name), (mask[:, yc].astype(np.uint8) * 255))

    surface_mm2 = None
    stl_url = None

    try:
        verts, faces, _, _ = measure.marching_cubes(
            mask.astype(np.uint8), level=0.5, spacing=tuple(spacing[::-1])
        )

        tri_verts = verts[faces]
        v1 = tri_verts[:, 1, :] - tri_verts[:, 0, :]
        v2 = tri_verts[:, 2, :] - tri_verts[:, 0, :]
        cross = np.linalg.norm(np.cross(v1, v2), axis=1)
        surface_mm2 = float(np.sum(0.5 * cross))

        stl_name = f"{uid}_head.stl"
        stl_path = os.path.join(base_out, stl_name)
        _save_ascii_stl(verts, faces, stl_path, solid_name=f"seg3d_{uid}")
        stl_url = _pub(stl_name)

    except Exception as e:
        print(f"Error STL: {e}")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO segmentacion3d
          (session_id, user_id, n_slices, volume_mm3, surface_mm2,
           bbox_x_mm, bbox_y_mm, bbox_z_mm, mask_npy_path,
           thumb_axial, thumb_sagittal, thumb_coronal)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            session_id,
            int(user_id),
            int(mask.shape[0]),
            float(volume_mm3),
            (float(surface_mm2) if surface_mm2 is not None else None),
            mask.shape[2] * spacing[2],
            mask.shape[1] * spacing[1],
            mask.shape[0] * spacing[0],
            _pub(mask_name),
            _pub(ax_name),
            _pub(sg_name),
            _pub(cr_name),
        ),
    )
    seg3d_id = int(cur.fetchone()[0])
    conn.commit()
    cur.close()
    conn.close()

    return {
        "message": "Segmentación 3D creada",
        "seg3d_id": seg3d_id,
        "volume_mm3": float(volume_mm3),
        "surface_mm2": (float(surface_mm2) if surface_mm2 else None),
        "thumbs": {
            "axial": _pub(ax_name),
            "sagittal": _pub(sg_name),
            "coronal": _pub(cr_name),
        },
        "bbox": {
            "x_mm": mask.shape[2] * spacing[2],
            "y_mm": mask.shape[1] * spacing[1],
            "z_mm": mask.shape[0] * spacing[0],
        },
        "n_slices": mask.shape[0],
        "modality": modality,
        "spacing_mm": {"z": spacing[0], "y": spacing[1], "x": spacing[2]},
        "stl_url": stl_url,
    }


# ==============================================================
# LISTAR Y BORRAR — EXACTO COMO LO TENÍAS
# ==============================================================

def listar_segmentaciones_3d(session_id: str, user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, n_slices, volume_mm3, surface_mm2,
               bbox_x_mm, bbox_y_mm, bbox_z_mm,
               mask_npy_path, thumb_axial, thumb_sagittal, thumb_coronal, created_at
        FROM segmentacion3d
        WHERE session_id = %s AND user_id = %s
        ORDER BY created_at DESC
        """,
        (session_id, user_id),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    out = []
    for r in rows:
        out.append(
            {
                "id": r[0],
                "n_slices": r[1],
                "volume_mm3": float(r[2]),
                "surface_mm2": (float(r[3]) if r[3] else None),
                "bbox_x_mm": float(r[4]),
                "bbox_y_mm": float(r[5]),
                "bbox_z_mm": float(r[6]),
                "mask_npy_path": r[7],
                "thumb_axial": r[8],
                "thumb_sagittal": r[9],
                "thumb_coronal": r[10],
                "created_at": r[11].isoformat() if r[11] else None,
            }
        )
    return out


def borrar_segmentacion_3d(seg3d_id: int, user_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT session_id, mask_npy_path, thumb_axial, thumb_sagittal, thumb_coronal FROM segmentacion3d WHERE id = %s AND user_id = %s",
        (seg3d_id, user_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return False

    session_id, npy_pub, ax_pub, sg_pub, cr_pub = row
    base = _seg3d_dir(session_id)

    cur.execute("DELETE FROM segmentacion3d WHERE id = %s AND user_id = %s", (seg3d_id, user_id))
    conn.commit()
    cur.close()
    conn.close()

    def rm(pub_path):
        if not pub_path:
            return
        fname = os.path.basename(pub_path)
        p = os.path.join(base, fname)
        if os.path.isfile(p):
            try:
                os.remove(p)
            except:
                pass

    rm(npy_pub)
    rm(ax_pub)
    rm(sg_pub)
    rm(cr_pub)

    try:
        if os.path.isdir(base) and not os.listdir(base):
            os.rmdir(base)
    except:
        pass

    return True

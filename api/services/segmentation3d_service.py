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
from config.paths import SERIES_DIR, SEGMENTATIONS_3D_DIR





# ========= Helpers de rutas corregidos =========

def _serie_dir(session_id: str):
    """
    Carpeta persistente donde se guardan los DICOM:
    /data/series/<session_id>/
    """
    d = SERIES_DIR / session_id
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def _seg3d_dir(session_id: str):
    """
    Carpeta persistente de segmentaciones 3D:
    /data/segmentations3d/<session_id>/
    """
    d = SEGMENTATIONS_3D_DIR / session_id
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


# ========= Helpers extra =========

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


# ========= Carga robusta del volumen 3D =========

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

    # Ordenamiento de cortes...
    enriched = []
    for p in entries:
        ds = pydicom.dcmread(p, force=True, stop_before_pixels=True)
        modality = str(getattr(ds, "Modality", "")).upper()

        z = None
        ipp = getattr(ds, "ImagePositionPatient", None)
        if isinstance(ipp, (list, tuple)) and len(ipp) == 3:
            try:
                z = float(ipp[2])
            except Exception:
                z = None

        inst = getattr(ds, "InstanceNumber", None)
        inst = int(inst) if inst is not None else None
        enriched.append((p, modality, z, inst))

    def _sort_key(t):
        p, modality, z, inst = t
        if z is not None:
            return (0, z)
        if inst is not None:
            return (1, inst)
        return (2, os.path.basename(p))

    enriched.sort(key=_sort_key)

    # Segunda pasada: validar resoluciones
    tmp_slices = []
    shape_counts = {}
    z_values_all = []

    for p, modality, z, _ in enriched:
        ds = pydicom.dcmread(p, force=True)

        try:
            arr = ds.pixel_array
        except:
            continue

        if arr.ndim == 3:
            if arr.shape[-1] == 3:
                continue
            if arr.shape[0] > 1 and arr.shape[1] == arr.shape[2]:
                arr = arr[0]
            if arr.ndim == 3:
                continue

        if arr.ndim != 2:
            continue

        arr = arr.astype(np.float32)
        shape = arr.shape
        shape_counts[shape] = shape_counts.get(shape, 0) + 1

        tmp_slices.append((arr, ds, z))
        if z is not None:
            z_values_all.append(z)

    if not tmp_slices:
        raise ValueError("No se pudieron leer píxeles DICOM válidos.")

    target_shape = max(shape_counts.items(), key=lambda kv: kv[1])[0]

    slices = []
    z_values = []
    for arr, ds, z in tmp_slices:
        if arr.shape != target_shape:
            continue
        slices.append((arr, ds))
        if z is not None:
            z_values.append(z)

    if not slices:
        raise ValueError("No se encontraron slices consistentes.")

    # Casos especiales: 1 o 2 cortes
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
        if hasattr(ds0, "PixelSpacing"):
            px_y, px_x = [float(v) for v in ds0.PixelSpacing]
    except:
        pass

    slice_thk = None
    try:
        slice_thk = float(getattr(ds0, "SliceThickness", None))
    except:
        slice_thk = None

    dz = None
    if len(z_values) >= 2:
        z_sorted = np.sort(np.array(z_values))
        diffs = np.diff(z_sorted)
        diffs = diffs[np.abs(diffs) > 1e-6]
        if diffs.size > 0:
            dz = float(np.median(np.abs(diffs)))

    if dz is None:
        sbs = getattr(ds0, "SpacingBetweenSlices", None)
        if sbs is not None:
            try:
                dz = float(sbs)
            except:
                dz = None

    if dz is None and slice_thk is not None:
        dz = slice_thk

    if dz is None or dz <= 0:
        dz = 1.0

    spacing = (dz, float(px_y), float(px_x))
    vol = np.stack([s[0] for s in slices], axis=0)

    modality0 = str(getattr(ds0, "Modality", "")).upper()

    if modality0 == "CT":
        slope = float(getattr(ds0, "RescaleSlope", 1.0))
        intercept = float(getattr(ds0, "RescaleIntercept", 0.0))
        vol = vol * slope + intercept
        vol = np.clip(vol, -1024, 4000)

    return vol, spacing, modality0


# ========= Segmentación 3D principal =========

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
    out_dir = _seg3d_dir(session_id)

    if vol.size > 2_000_000:
        try:
            vol = median_filter(vol, size=3)
        except:
            pass

    # === Binarización ===
    mask = None

    if modality == "CT":
        v = vol[np.isfinite(vol)]
        if v.size == 0:
            mask = np.zeros_like(vol, bool)
        else:
            presets = {
                "ct_bone": (250, 4000),
                "ct_head": (-300, 3000),
                "ct_soft": (-150, 300),
                "ct_lung": (-1000, -300),
            }

            if preset in presets:
                lo, hi = presets[preset]
            elif thr_min is not None or thr_max is not None:
                lo = thr_min if thr_min is not None else np.percentile(v, 40)
                hi = thr_max if thr_max is not None else np.percentile(v, 99)
            else:
                hu_range = v.max() - v.min()
                if hu_range > 200:
                    lo, hi = 150, 4000
                else:
                    lo, hi = np.percentile(v, [40, 99])
                    vnorm = (vol - lo) / (hi - lo + 1e-6)
                    mask = vnorm > 0.6

            if mask is None:
                mask = (vol >= lo) & (vol <= hi)

    else:
        v = vol[np.isfinite(vol)]
        if v.size == 0:
            mask = np.zeros_like(vol, bool)
        else:
            lo, hi = np.percentile(v, [2, 98])
            if hi <= lo:
                hi = lo + 1
            vclip = np.clip(vol, lo, hi)
            vclip = (vclip - lo) / (hi - lo + 1e-6)
            try:
                thr = threshold_otsu(vclip[vclip > 0])
                mask = vclip > thr
            except:
                mask = vclip > np.percentile(vclip, 95)

    if mask is None or mask.ndim != 3:
        raise ValueError("máscara 3D inválida")

    r_vox = max(1, int(round(close_radius_mm / max(float(np.mean(spacing)), 1e-6))))

    mask = binary_closing(mask, footprint=ball(r_vox))
    try:
        mask = binary_fill_holes(mask)
    except:
        pass

    mask = morphology.remove_small_objects(mask, min_size=int(min_size_voxels))

    if mask.sum() == 0:
        return {
            "message": "Segmentación 3D vacía",
            "volume_mm3": 0.0,
            "surface_mm2": None,
            "thumbs": {},
            "warning": True,
            "modality": modality,
            "spacing_mm": {"z": spacing[0], "y": spacing[1], "x": spacing[2]},
            "stl_url": None,
        }

    labels = measure.label(mask)
    if labels.max() > 0:
        counts = np.bincount(labels.ravel())
        biggest = np.argmax(counts[1:]) + 1
        mask = labels == biggest

    # === Métricas ===
    voxel_mm3 = spacing[0] * spacing[1] * spacing[2]
    voxels = mask.sum()
    volume_mm3 = voxels * voxel_mm3

    uid = f"{int(time.time()*1e6)}_{uuid.uuid4().hex[:8]}"

    def _pub(name):
        return f"/static/segmentations3d/{session_id}/{name}"

    mask_name = f"{uid}_mask.npy"
    ax_name = f"{uid}_axial.png"
    sg_name = f"{uid}_sagittal.png"
    cr_name = f"{uid}_coronal.png"

    np.save(os.path.join(out_dir, mask_name), mask.astype(np.uint8))

    zc = mask.shape[0] // 2
    yc = mask.shape[1] // 2
    xc = mask.shape[2] // 2

    io.imsave(os.path.join(out_dir, ax_name), mask[zc].astype(np.uint8) * 255)
    io.imsave(os.path.join(out_dir, sg_name), mask[:, :, xc].astype(np.uint8) * 255)
    io.imsave(os.path.join(out_dir, cr_name), mask[:, yc].astype(np.uint8) * 255)

    # STL
    stl_url = None
    surface_mm2 = None

    try:
        verts, faces, _, _ = measure.marching_cubes(mask.astype(np.uint8), 0.5, spacing=spacing[::-1])

        tri = verts[faces]
        v1 = tri[:, 1, :] - tri[:, 0, :]
        v2 = tri[:, 2, :] - tri[:, 0, :]
        surface_mm2 = float(np.sum(0.5 * np.linalg.norm(np.cross(v1, v2), axis=1)))

        stl_name = f"{uid}.stl"
        stl_path = os.path.join(out_dir, stl_name)
        _save_ascii_stl(verts, faces, stl_path)

        stl_url = _pub(stl_name)

    except Exception as e:
        print("Error STL:", e)

    # Guardar en BD
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO segmentacion3d
          (session_id, user_id, n_slices, volume_mm3, surface_mm2,
           bbox_x_mm, bbox_y_mm, bbox_z_mm, mask_npy_path,
           thumb_axial, thumb_sagittal, thumb_coronal)
        VALUES (%s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s)
        RETURNING id
        """,
        (
            session_id,
            user_id,
            mask.shape[0],
            volume_mm3,
            surface_mm2,
            mask.shape[2] * spacing[2],
            mask.shape[1] * spacing[1],
            mask.shape[0] * spacing[0],
            _pub(mask_name),
            _pub(ax_name),
            _pub(sg_name),
            _pub(cr_name),
        ),
    )
    seg3d_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    return {
        "message": "Segmentación 3D creada",
        "seg3d_id": seg3d_id,
        "volume_mm3": volume_mm3,
        "surface_mm2": surface_mm2,
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
        "spacing_mm": {"z": spacing[0], "y": spacing[1], "x": spacing[2]},
        "stl_url": stl_url,
    }


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
                "surface_mm2": (float(r[3]) if r[3] is not None else None),
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
        """
        SELECT session_id, mask_npy_path, thumb_axial, thumb_sagittal, thumb_coronal
        FROM segmentacion3d
        WHERE id = %s AND user_id = %s
        """,
        (seg3d_id, user_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return False

    session_id, npy_pub, ax_pub, sg_pub, cr_pub = row
    folder = _seg3d_dir(session_id)

    cur.execute(
        "DELETE FROM segmentacion3d WHERE id = %s AND user_id = %s",
        (seg3d_id, user_id),
    )
    conn.commit()
    cur.close()
    conn.close()

    def rm(pub_path):
        if not pub_path:
            return
        fname = os.path.basename(pub_path)
        fpath = os.path.join(folder, fname)
        if os.path.isfile(fpath):
            try:
                os.remove(fpath)
            except:
                pass

    rm(npy_pub)
    rm(ax_pub)
    rm(sg_pub)
    rm(cr_pub)

    try:
        if os.path.isdir(folder) and not os.listdir(folder):
            os.rmdir(folder)
    except:
        pass

    return True

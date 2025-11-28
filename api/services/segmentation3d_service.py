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


def _serie_dir(session_id: str):
    return os.path.abspath(os.path.join("api", "static", "series", session_id))


def _seg3d_dir(session_id: str):
    return os.path.abspath(os.path.join("api", "static", "segmentations3d", session_id))


# ========= Helpers extra =========

def _interpolar_slice(arr1: np.ndarray, arr2: np.ndarray) -> np.ndarray:
    """
    Genera un corte intermedio entre dos slices 2D (H, W) por interpolación lineal.
    """
    return ((arr1.astype(np.float32) + arr2.astype(np.float32)) / 2.0).astype(arr1.dtype)


def _save_ascii_stl(verts: np.ndarray, faces: np.ndarray, filepath: str, solid_name: str = "seg3d"):
    """
    Guarda un STL ASCII simple a partir de vértices y caras.
    verts: (N, 3), faces: (M, 3) índices a verts.
    """
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"solid {solid_name}\n")
        for tri in faces:
            v1 = verts[tri[0]]
            v2 = verts[tri[1]]
            v3 = verts[tri[2]]

            # Normal de la cara
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


# ========= Carga y construcción del volumen 3D =========

def _load_stack(session_id: str):
    """
    Carga la serie DICOM asociada a session_id y devuelve:
      - vol: volumen 3D (Z, Y, X)
      - spacing: (dz, dy, dx) en mm
      - modality0: modalidad principal (CT/MR/...)

    Robusto:
      - Filtra SC, RGB, slices sin pixel_array.
      - Lee TODOS los slices válidos.
      - Elige la resolución (shape) más frecuente del ZIP.
      - Si hay exactamente 2 cortes -> interpola un tercero.
      - Si hay 1 corte -> lo replica para crear volumen mínimo.
    """
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

    # ---- Ordenar cortes por Z o InstanceNumber ----
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

    # ---- 1ª pasada: leer TODOS los slices válidos y contar shapes ----
    tmp_slices = []          # (arr, ds, z)
    shape_counts = {}        # {(H, W): count}
    z_values_all = []        # z de todos los candidatos (para spacing)

    for p, modality, z, _ in enriched:
        ds = pydicom.dcmread(p, force=True)

        # Filtrar SC
        if str(getattr(ds, "Modality", "")).upper() == "SC":
            print(f"⚠️ Slice descartado por ser SC: {p}")
            continue

        # pixel_array
        try:
            arr = ds.pixel_array
        except Exception:
            print(f"⚠️ Slice descartado: no tiene pixel_array → {p}")
            continue

        # Manejo RGB / multi-frame
        if arr.ndim == 3:
            if arr.shape[-1] == 3:
                print(f"⚠️ Slice descartado por ser RGB: {arr.shape} → {p}")
                continue
            if arr.shape[0] > 1 and arr.shape[1] == arr.shape[2]:
                arr = arr[0]
            if arr.ndim == 3:
                print(f"⚠️ Slice descartado por shape 3D no soportado: {arr.shape} → {p}")
                continue

        if arr.ndim != 2:
            print(f"⚠️ Slice descartado por no ser 2D: ndim={arr.ndim}, shape={arr.shape} → {p}")
            continue

        arr = arr.astype(np.float32)
        shape = arr.shape
        shape_counts[shape] = shape_counts.get(shape, 0) + 1

        tmp_slices.append((arr, ds, z))
        if z is not None:
            z_values_all.append(z)

    if not tmp_slices:
        raise ValueError("No se pudieron leer píxeles DICOM válidos para construir el volumen 3D.")

    # ---- Elegir la resolución principal (shape más frecuente) ----
    target_shape = max(shape_counts.items(), key=lambda kv: kv[1])[0]
    print(f"✅ Resolución principal seleccionada: {target_shape} ({shape_counts[target_shape]} cortes)")

    # ---- 2ª pasada: quedarnos sólo con esos cortes ----
    slices = []
    z_values = []
    for arr, ds, z in tmp_slices:
        if arr.shape != target_shape:
            print(f"⚠️ Slice descartado por otra resolución: {arr.shape} != {target_shape}")
            continue
        slices.append((arr, ds))
        if z is not None:
            z_values.append(z)

    if not slices:
        raise ValueError("No se encontraron slices con resolución consistente para el volumen 3D.")

    # ---- Casos especiales de pocos cortes ----
    if len(slices) == 1:
        # Volumen sintético por replicación de la única lámina
        print("⚠️ Solo 1 corte válido → replicando para crear volumen sintético (no anatómico).")
        arr, ds0 = slices[0]
        slices = [(arr, ds0), (arr.copy(), ds0), (arr.copy(), ds0)]
    elif len(slices) == 2:
        print("⚠️ Solo 2 cortes válidos → generando corte interpolado.")
        arr1, ds1 = slices[0]
        arr2, ds2 = slices[1]
        arr_mid = _interpolar_slice(arr1, arr2)
        slices = [(arr1, ds1), (arr_mid, ds1), (arr2, ds2)]

    # A partir de aquí siempre hay al menos 3 cortes sintéticos o reales
    # ===== ESPACIADOS =====
    ds0 = slices[0][1]

    # Pixel spacing (Y, X)
    px_y, px_x = 1.0, 1.0
    try:
        if hasattr(ds0, "PixelSpacing"):
            px_y, px_x = [float(v) for v in ds0.PixelSpacing]
        elif hasattr(ds0, "ImagerPixelSpacing"):
            px_y, px_x = [float(v) for v in ds0.ImagerPixelSpacing]
    except Exception:
        pass

    # Slice thickness
    slice_thk = None
    try:
        slice_thk = float(getattr(ds0, "SliceThickness", None))
    except Exception:
        slice_thk = None

    dz = None
    if len(z_values) >= 2:
        z_sorted = np.sort(np.array(z_values, dtype=np.float64))
        diffs = np.diff(z_sorted)
        diffs = diffs[np.isfinite(diffs) & (np.abs(diffs) > 1e-6)]
        if diffs.size > 0:
            dz = float(np.median(np.abs(diffs)))

    if dz is None:
        sbs = getattr(ds0, "SpacingBetweenSlices", None)
        if sbs is not None:
            try:
                dz = float(sbs)
            except Exception:
                dz = None

    if dz is None and slice_thk is not None:
        dz = slice_thk

    if dz is None or dz <= 0:
        dz = 1.0

    spacing = (dz, float(px_y), float(px_x))

    # ===== Volumen 3D =====
    vol = np.stack([s[0] for s in slices], axis=0)
    modality0 = str(getattr(ds0, "Modality", "")).upper()

    # Normalización HU si es CT
    if modality0 == "CT":
        slope = float(getattr(ds0, "RescaleSlope", 1.0))
        intercept = float(getattr(ds0, "RescaleIntercept", 0.0))
        vol = vol * slope + intercept
        vol = np.clip(vol, -1024, 4000)

    return vol, spacing, modality0


# ========= Segmentación 3D + STL =========

def segmentar_serie_3d(
    session_id: str,
    user_id: int,
    preset: Optional[str] = None,
    thr_min: Optional[float] = None,
    thr_max: Optional[float] = None,
    min_size_voxels: int = 2000,
    close_radius_mm: float = 1.5,
) -> dict:
    """
    Segmentación 3D robusta con presets por modalidad.
    - Maneja series con 1 o 2 cortes (volumen sintético / interpolado).
    - Intenta varios thresholds y fallbacks.
    - Genera STL a partir de la máscara 3D.
    """
    vol, spacing, modality = _load_stack(session_id)  # (Z,Y,X)
    os.makedirs(_seg3d_dir(session_id), exist_ok=True)

    # ===== 1) Pre-procesado suave (reduce ruido) =====
    if vol.size > 2_000_000:
        try:
            vol = median_filter(vol, size=3)
        except Exception:
            pass

    # ===== 2) Binarización según modalidad/preset =====
    mask = None

    if modality == "CT":
        v = vol[np.isfinite(vol)]
        if v.size == 0:
            mask = np.zeros_like(vol, dtype=bool)
        else:
            presets = {
                "ct_bone": (250.0, 4000.0),
                "ct_head": (-300.0, 3000.0),
                "ct_soft": (-150.0, 300.0),
                "ct_lung": (-1000.0, -300.0),
            }

            if preset in presets:
                tmin, tmax = presets[preset]
            elif thr_min is not None or thr_max is not None:
                lo = np.percentile(v, 40)
                hi = np.percentile(v, 99)
                tmin = thr_min if thr_min is not None else lo
                tmax = thr_max if thr_max is not None else hi
            else:
                # Adaptativo: HU normales vs CT raro
                hu_range = float(v.max() - v.min())
                if hu_range > 200:
                    tmin, tmax = 150.0, 4000.0
                else:
                    lo, hi = np.percentile(v, [40, 99])
                    vnorm = (vol - lo) / (hi - lo + 1e-6)
                    vnorm = np.clip(vnorm, 0, 1)
                    mask = vnorm > 0.6

            if mask is None:
                mask = (vol >= tmin) & (vol <= tmax)

            # Fallback si casi no hay voxeles
            if mask.sum() < 200:
                print("⚠️ Máscara CT muy pequeña, aplicando umbral adaptativo.")
                lo, hi = np.percentile(v, [40, 99])
                vnorm = (vol - lo) / (hi - lo + 1e-6)
                vnorm = np.clip(vnorm, 0, 1)
                mask = vnorm > 0.5

    else:
        # MR u otra modalidad: Otsu global tras normalización
        v = vol[np.isfinite(vol)]
        if v.size == 0:
            mask = np.zeros_like(vol, dtype=bool)
        else:
            lo, hi = np.percentile(v, [2, 98])
            if hi <= lo:
                hi = lo + 1.0
            vclip = np.clip(vol, lo, hi)
            vclip = (vclip - lo) / (hi - lo + 1e-6)
            try:
                thr = float(threshold_otsu(vclip[vclip > 0]))
                mask = vclip > thr
            except Exception:
                thr = float(np.percentile(vclip, 95))
                mask = vclip > thr

    # Seguridad: asegurar que mask sea 3D
    if mask is None or mask.ndim != 3:
        raise ValueError(f"La máscara 3D no es válida. ndim={getattr(mask, 'ndim', None)}")

    # ===== 3) Morfología 3D =====
    r_vox = max(1, int(round(close_radius_mm / max(float(np.mean(spacing)), 1e-6))))
    mask = binary_closing(mask, footprint=ball(r_vox))
    try:
        mask = binary_fill_holes(mask)
    except Exception:
        pass

    mask = morphology.remove_small_objects(mask, min_size=int(min_size_voxels))

    # Fallback extra: si se quedó sin voxeles, intentar con min_size más pequeño
    if mask.sum() == 0:
        print("⚠️ Máscara vacía tras remove_small_objects, reintentando con tamaño mínimo pequeño.")
        mask_tmp = binary_closing(mask, footprint=ball(r_vox))
        try:
            mask_tmp = binary_fill_holes(mask_tmp)
        except Exception:
            pass
        mask_tmp = morphology.remove_small_objects(mask_tmp, min_size=100)
        if mask_tmp.sum() > 0:
            mask = mask_tmp

    labels = measure.label(mask, connectivity=3)
    if labels.max() > 0:
        counts = np.bincount(labels.ravel())
        largest = int(np.argmax(counts[1:]) + 1)
        mask = labels == largest
    else:
        mask = np.zeros_like(mask, dtype=bool)

    # ===== 4) Métricas =====
    voxel_mm3 = float(spacing[0] * spacing[1] * spacing[2])
    voxels = int(mask.sum())
    volume_mm3 = float(voxels * voxel_mm3)

    base_out = _seg3d_dir(session_id)
    uid = f"{int(time.time()*1e6)}_{uuid.uuid4().hex[:8]}"

    def _pub(name: str) -> str:
        return f"/static/segmentations3d/{session_id}/{name}"

    mask_name = f"{uid}_mask.npy"
    ax_name   = f"{uid}_axial.png"
    sg_name   = f"{uid}_sagittal.png"
    cr_name   = f"{uid}_coronal.png"

    if mask.ndim != 3:
        raise ValueError(f"La máscara 3D tiene dimensiones inválidas: shape={mask.shape}")

    # Si el volumen es demasiado "plano" en Z, lo replicamos un poco
    if mask.shape[0] < 3:
        mask = np.repeat(mask, 3, axis=0)

    zc = mask.shape[0] // 2
    yc = mask.shape[1] // 2
    xc = mask.shape[2] // 2

    np.save(os.path.join(base_out, mask_name), mask.astype(np.uint8))

    io.imsave(os.path.join(base_out, ax_name), (mask[zc].astype(np.uint8) * 255))
    io.imsave(os.path.join(base_out, sg_name), (mask[:, :, xc].astype(np.uint8) * 255))
    io.imsave(os.path.join(base_out, cr_name), (mask[:, yc].astype(np.uint8) * 255))

    # Si no hay voxeles, avisar pero no romper
    if voxels == 0:
        return {
            "message": "Segmentación 3D vacía (los DICOM no contienen suficiente información útil).",
            "volume_mm3": 0.0,
            "surface_mm2": None,
            "thumbs": {
                "axial": _pub(ax_name),
                "sagittal": _pub(sg_name),
                "coronal": _pub(cr_name),
            },
            "warning": True,
            "modality": modality,
            "spacing_mm": {"z": spacing[0], "y": spacing[1], "x": spacing[2]},
            "stl_url": None,
        }

    coords = np.argwhere(mask)
    zmin, ymin, xmin = coords.min(axis=0)
    zmax, ymax, xmax = coords.max(axis=0)
    bbox_z_mm = float((zmax - zmin + 1) * spacing[0])
    bbox_y_mm = float((ymax - ymin + 1) * spacing[1])
    bbox_x_mm = float((xmax - xmin + 1) * spacing[2])

    # ===== 5) Superficie y STL =====
    surface_mm2 = None
    stl_url = None
    try:
        # marching_cubes devuelve la superficie de la máscara
        verts, faces, _, _ = measure.marching_cubes(
            mask.astype(np.uint8), level=0.5, spacing=tuple(spacing[::-1])
        )

        # Área superficial
        tri_verts = verts[faces]
        v1 = tri_verts[:, 1, :] - tri_verts[:, 0, :]
        v2 = tri_verts[:, 2, :] - tri_verts[:, 0, :]
        cross = np.linalg.norm(np.cross(v1, v2), axis=1)
        surface_mm2 = float(np.sum(0.5 * cross))

        # Guardar STL
        stl_name = f"{uid}_head.stl"
        stl_path = os.path.join(base_out, stl_name)
        _save_ascii_stl(verts, faces, stl_path, solid_name=f"seg3d_{uid}")
        stl_url = _pub(stl_name)

    except Exception as e:
        print(f"⚠️ Error al generar superficie/STL: {e}")
        surface_mm2 = None
        stl_url = None

    # ===== 6) Guardar en DB =====
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
            float(bbox_x_mm),
            float(bbox_y_mm),
            float(bbox_z_mm),
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
        "surface_mm2": (float(surface_mm2) if surface_mm2 is not None else None),
        "thumbs": {
            "axial": _pub(ax_name),
            "sagittal": _pub(sg_name),
            "coronal": _pub(cr_name),
        },
        "bbox": {
            "x_mm": float(bbox_x_mm),
            "y_mm": float(bbox_y_mm),
            "z_mm": float(bbox_z_mm),
        },
        "n_slices": int(mask.shape[0]),
        "modality": modality,
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

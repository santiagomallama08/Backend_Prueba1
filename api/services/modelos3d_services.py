import os
import time
import struct
import numpy as np
from skimage import measure

from config.db_config import get_connection

# 📌 Importar rutas persistentes desde config.paths (NO desde main.py)
from config.paths import MODELOS3D_DIR, SEGMENTATIONS_3D_DIR

# Reutilizamos helpers desde segmentación 3D
from api.services.segmentation3d_service import _load_stack


# -----------------------------------------------------------
# 1) Carpeta persistente del STL
# -----------------------------------------------------------
def _models_dir(session_id: str) -> str:
    """
    /data/static/modelos3d/<session_id>/
    """
    base = MODELOS3D_DIR / session_id
    base.mkdir(parents=True, exist_ok=True)
    return str(base)


def _public_models_dir(session_id: str) -> str:
    return f"/static/modelos3d/{session_id}"


# -----------------------------------------------------------
# 2) Escritura de STL binario
# -----------------------------------------------------------
def _write_binary_stl(path: str, vertices: np.ndarray, faces: np.ndarray, name: bytes = b"dicom_mesh") -> None:
    vertices = np.asarray(vertices, dtype=np.float32)
    faces = np.asarray(faces, dtype=np.int32)

    with open(path, "wb") as f:
        header = (name[:80]).ljust(80, b" ")
        f.write(header)
        f.write(struct.pack("<I", faces.shape[0]))

        zero_normal = struct.pack("<3f", 0.0, 0.0, 0.0)
        for tri in faces:
            f.write(zero_normal)
            for vidx in tri:
                vx, vy, vz = vertices[vidx]
                f.write(struct.pack("<3f", vx, vy, vz))
            f.write(struct.pack("<H", 0))


# -----------------------------------------------------------
# 3) Resolver ruta absoluta de mask.npy
# -----------------------------------------------------------
def _resolve_mask_npy_abs(session_id: str, mask_npy_public: str) -> str:
    """
    Convierte:
        /static/segmentations3d/<session_id>/mask.npy
    en:
        /data/static/segmentations3d/<session_id>/mask.npy
    """

    if mask_npy_public.startswith("/static/"):
        rel = mask_npy_public[len("/static/"):]  # segmentations3d/....
        abs_path = SEGMENTATIONS_3D_DIR.parent / rel
        return str(abs_path)

    # fallback
    return str(SEGMENTATIONS_3D_DIR / session_id / os.path.basename(mask_npy_public))


# -----------------------------------------------------------
# 4) EXPORTAR STL DESDE MASCARA 3D
# -----------------------------------------------------------
def exportar_stl_desde_seg3d(session_id: str, user_id: int, seg3d_id: int | None = None):
    conn = get_connection()
    cur = conn.cursor()

    # Obtener la última segmentación o una específica
    if seg3d_id is None:
        cur.execute(
            """
            SELECT id, mask_npy_path
            FROM segmentacion3d
            WHERE session_id = %s AND user_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (session_id, user_id),
        )
    else:
        cur.execute(
            """
            SELECT id, mask_npy_path
            FROM segmentacion3d
            WHERE id = %s AND session_id = %s AND user_id = %s
            """,
            (seg3d_id, session_id, user_id),
        )

    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        raise ValueError("No hay segmentación 3D disponible para exportar.")

    seg3d_id = int(row[0])
    mask_npy_public = row[1]

    # Resolver ruta absoluta
    mask_abs = _resolve_mask_npy_abs(session_id, mask_npy_public)

    if not os.path.isfile(mask_abs):
        raise FileNotFoundError(f"No existe mask.npy en {mask_abs}")

    # Cargar máscara
    mask = np.load(mask_abs) > 0

    # Spacing del estudio
    _, spacing, _ = _load_stack(session_id)

    # Marching Cubes
    verts, faces, _, _ = measure.marching_cubes(
        mask.astype(np.uint8),
        level=0.5,
        spacing=spacing[::-1],
    )

    num_vertices = verts.shape[0]
    num_faces = faces.shape[0]

    # Carpeta persistente del STL
    out_dir = _models_dir(session_id)
    timestamp = int(time.time())
    stl_filename = f"{timestamp}_seg3d_{seg3d_id}.stl"
    stl_abs_path = os.path.join(out_dir, stl_filename)

    # Guardar STL
    _write_binary_stl(stl_abs_path, verts, faces)
    file_size_bytes = os.path.getsize(stl_abs_path)

    stl_public_url = f"{_public_models_dir(session_id)}/{stl_filename}"

    # Guardar en base de datos
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO modelo3d (session_id, user_id, seg3d_id, path_stl,
                              num_vertices, num_caras, file_size_bytes)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, created_at
        """,
        (
            session_id, user_id, seg3d_id, stl_public_url,
            num_vertices, num_faces, file_size_bytes,
        ),
    )

    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    modelo_id, created_at = row

    return {
        "message": "STL generado correctamente",
        "id": modelo_id,
        "seg3d_id": seg3d_id,
        "path_stl": stl_public_url,
        "num_vertices": num_vertices,
        "num_caras": num_faces,
        "file_size_bytes": file_size_bytes,
        "created_at": created_at.isoformat() if created_at else None,
    }


# -----------------------------------------------------------
# 5) LISTAR MODELOS 3D
# -----------------------------------------------------------
def listar_modelos3d(session_id: str, user_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, seg3d_id, path_stl, num_vertices, num_caras, file_size_bytes, created_at
        FROM modelo3d
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
                "seg3d_id": r[1],
                "path_stl": r[2],
                "num_vertices": r[3],
                "num_caras": r[4],
                "file_size_bytes": r[5],
                "created_at": r[6].isoformat() if r[6] else None,
            }
        )

    return out


# -----------------------------------------------------------
# 6) ELIMINAR MODELO STL
# -----------------------------------------------------------
def borrar_modelo3d(modelo_id: int, user_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT session_id, path_stl FROM modelo3d WHERE id = %s AND user_id = %s",
        (modelo_id, user_id),
    )
    row = cur.fetchone()

    if not row:
        return False

    session_id, path_pub = row

    # Eliminar registro
    cur.execute(
        "DELETE FROM modelo3d WHERE id = %s AND user_id = %s",
        (modelo_id, user_id),
    )
    conn.commit()
    cur.close()
    conn.close()

    # Eliminar archivo STL
    if path_pub.startswith("/static/"):
        rel = path_pub[len("/static/"):]
        abs_path = MODELOS3D_DIR.parent / rel

        if abs_path.is_file():
            try:
                abs_path.unlink()
            except:
                pass

    # Eliminar carpeta vacía
    folder = MODELOS3D_DIR / session_id
    try:
        if folder.is_dir() and not os.listdir(folder):
            folder.rmdir()
    except:
        pass

    return True

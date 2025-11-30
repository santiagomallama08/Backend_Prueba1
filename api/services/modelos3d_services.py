import os
import time
import struct
import numpy as np
from skimage import measure

from config.db_config import get_connection

# Importar rutas persistentes desde el volumen
from main import MODELOS3D_DIR     # /data/static/modelos3d
from main import SEG3D_DIR         # /data/static/segmentations3d

# Reutilizamos helpers desde la carga del stack
from api.services.segmentation3d_service import _load_stack


# -----------------------------------------------------------
# 1) Carpeta para STL en volumen persistente
# -----------------------------------------------------------
def _models_dir(session_id: str) -> str:
    """
    Carpeta persistente:
    /data/static/modelos3d/<session_id>/
    """
    base = MODELOS3D_DIR / session_id
    base.mkdir(parents=True, exist_ok=True)
    return str(base)


def _public_models_dir(session_id: str) -> str:
    """
    Ruta pública:
    /static/modelos3d/<session_id>/
    """
    return f"/static/modelos3d/{session_id}"


# -----------------------------------------------------------
# 2) Escritura de STL binario
# -----------------------------------------------------------
def _write_binary_stl(path: str, vertices: np.ndarray, faces: np.ndarray, name: str = b"dicom_mesh") -> None:
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
# 3) Resolver mask.npy desde volumen
# -----------------------------------------------------------
def _resolve_mask_npy_abs(session_id: str, mask_npy_path_public: str) -> str:
    """
    Convierte rutas públicas tipo:
    /static/segmentations3d/<session_id>/mask.npy
    en rutas absolutas dentro del volumen:
    /data/static/segmentations3d/<session_id>/mask.npy
    """

    # Si ya es absoluta y existe
    if os.path.isabs(mask_npy_path_public) and os.path.isfile(mask_npy_path_public):
        return mask_npy_path_public

    # Si viene como /static/segmentations3d/session/file
    if mask_npy_path_public.startswith("/static/"):
        rel = mask_npy_path_public[len("/static/"):]  # segmentations3d/<sid>/mask.npy
        abs_path = SEG3D_DIR.parent / rel  # BASE_STATIC_DIR / rel
        return str(abs_path)

    # Fallback: buscar en /data/static/segmentations3d/<session_id>
    candidate = SEG3D_DIR / session_id / os.path.basename(mask_npy_path_public)
    return str(candidate)


# -----------------------------------------------------------
# 4) EXPORTAR STL
# -----------------------------------------------------------
def exportar_stl_desde_seg3d(session_id: str, user_id: int, seg3d_id: int | None = None):
    # Buscar segmentación
    conn = get_connection()
    cur = conn.cursor()

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
    if not row:
        raise ValueError("No hay segmentación 3D disponible para exportar STL.")

    seg3d_id = int(row[0])
    mask_npy_public = row[1]
    cur.close()
    conn.close()

    # Resolver ruta absoluta en volumen
    mask_abs = _resolve_mask_npy_abs(session_id, mask_npy_public)
    if not os.path.isfile(mask_abs):
        raise FileNotFoundError(f"No se encontró mask.npy en {mask_abs}")

    mask = np.load(mask_abs)
    mask = mask > 0

    # Spacing
    _, spacing, _ = _load_stack(session_id)

    # Marching Cubes
    verts, faces, _, _ = measure.marching_cubes(
        mask.astype(np.uint8),
        level=0.5,
        spacing=spacing[::-1]
    )

    num_vertices = verts.shape[0]
    num_faces = faces.shape[0]

    # Carpeta persistente del STL
    out_dir = _models_dir(session_id)
    ts = int(time.time())
    stl_filename = f"{ts}_seg3d_{seg3d_id}.stl"
    stl_abs_path = os.path.join(out_dir, stl_filename)

    _write_binary_stl(stl_abs_path, verts, faces)

    file_size_bytes = int(os.path.getsize(stl_abs_path))

    # Ruta pública
    stl_pub = f"{_public_models_dir(session_id)}/{stl_filename}"

    # Guardar en DB
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
            session_id, user_id, seg3d_id, stl_pub,
            num_vertices, num_faces, file_size_bytes,
        ),
    )
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    modelo_id, created_at = row[0], row[1]

    return {
        "message": "STL generado",
        "id": modelo_id,
        "path_stl": stl_pub,
        "num_vertices": num_vertices,
        "num_caras": num_faces,
        "file_size_bytes": file_size_bytes,
        "seg3d_id": seg3d_id,
        "created_at": created_at.isoformat() if created_at else None,
    }


# -----------------------------------------------------------
# 5) LISTAR MODELOS 3D — No necesita cambios
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
# 6) ELIMINAR STL
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

    cur.execute(
        "DELETE FROM modelo3d WHERE id = %s AND user_id = %s",
        (modelo_id, user_id),
    )
    conn.commit()
    cur.close()
    conn.close()

    # Borrar archivo en volumen
    if path_pub.startswith("/static/"):
        rel = path_pub[len("/static/"):]  # modelos3d/<session_id>/file.stl
        abs_path = MODELOS3D_DIR.parent / rel
        abs_path = str(abs_path)

        if os.path.isfile(abs_path):
            try:
                os.remove(abs_path)
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

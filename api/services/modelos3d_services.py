# api/services/modelos3d_services.py
import os
import time
import struct
import numpy as np
from skimage import measure

from config.db_config import get_connection

# Reutilizamos el spacing desde la carga del volumen
from api.services.segmentation3d_service import _load_stack, _seg3d_dir


def _models_dir(session_id: str) -> str:
    """
    Carpeta absoluta donde se guardarán los STL:
    api/static/models/<session_id>/
    """
    base = os.path.abspath(os.path.join("api", "static", "models", session_id))
    os.makedirs(base, exist_ok=True)
    return base


def _public_models_dir(session_id: str) -> str:
    """
    Carpeta pública para servir por FastAPI/StaticFiles:
    /static/models/<session_id>/
    """
    return f"/static/models/{session_id}"


def _write_binary_stl(
    path: str, vertices: np.ndarray, faces: np.ndarray, name: str = b"dicom_mesh"
) -> None:
    """
    Escribe un STL binario simple. Un STL binario requiere:
    - 80 bytes de header
    - 4 bytes (uint32) con el número de triángulos
    - Por triángulo: 12 floats (normal + 3 vértices) + 2 bytes (attrib)
    """
    # Asegurar tipos
    vertices = np.asarray(vertices, dtype=np.float32)
    faces = np.asarray(faces, dtype=np.int32)

    with open(path, "wb") as f:
        header = (name[:80]).ljust(80, b" ")
        f.write(header)
        f.write(struct.pack("<I", faces.shape[0]))

        # Para cada cara, escribir normal (0,0,0) y vértices
        # (si quieres normales reales, puedes calcularlas)
        zero_normal = struct.pack("<3f", 0.0, 0.0, 0.0)
        for tri in faces:
            f.write(zero_normal)
            for vidx in tri:
                vx, vy, vz = vertices[vidx]
                f.write(struct.pack("<3f", vx, vy, vz))
            # attribute byte count
            f.write(struct.pack("<H", 0))


def _resolve_mask_npy_abs(session_id: str, mask_npy_path_public: str) -> str:
    """
    Convierte una ruta pública (p.ej., /static/segmentations3d/<session_id>/mask.npy)
    a una ruta absoluta en disco: api/static/segmentations3d/<session_id>/mask.npy
    """
    # Si ya viene absoluta, devolverla
    if os.path.isabs(mask_npy_path_public) and os.path.isfile(mask_npy_path_public):
        return mask_npy_path_public

    # Si es pública (empieza por /static), la mapeamos a api/static
    if mask_npy_path_public.startswith("/static/"):
        rel = mask_npy_path_public[
            len("/static/") :
        ]  # segmentations3d/<session_id>/mask.npy
        abs_path = os.path.abspath(os.path.join("api", "static", rel))
        return abs_path

    # Fallback: intentar dentro del dir seg3d
    base = _seg3d_dir(session_id)
    candidate = os.path.join(base, os.path.basename(mask_npy_path_public))
    return os.path.abspath(candidate)


def exportar_stl_desde_seg3d(
    session_id: str, user_id: int, seg3d_id: int | None = None
) -> dict:
    """
    - Busca la segmentación 3D más reciente (o la dada por seg3d_id) para session_id/user_id
    - Carga mask.npy
    - Obtiene spacing (mm) desde _load_stack(session_id)
    - Aplica marching_cubes con spacing en mm
    - Escribe STL en api/static/models/<session_id>/<timestamp>_seg3d_<id>.stl
    - Inserta registro en modelo3d y devuelve metadatos
    """
    conn = get_connection()
    cur = conn.cursor()

    # 1) Resolver qué seg3d usar
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
        cur.close()
        conn.close()
        raise ValueError("No hay segmentación 3D disponible para exportar STL.")

    seg3d_id = int(row[0])
    mask_npy_public = row[1]
    cur.close()
    conn.close()

    # 2) Cargar máscara y spacing
    mask_path_abs = _resolve_mask_npy_abs(session_id, mask_npy_public)
    if not os.path.isfile(mask_path_abs):
        raise FileNotFoundError(f"No se encontró mask.npy en {mask_path_abs}")

    mask = np.load(mask_path_abs)
    # Garantizar boolean/uint8
    mask = mask > 0

    # Obtener spacing en mm desde la serie
    _, spacing, _ = _load_stack(session_id)  # spacing = (dz, dy, dx) en mm

    # 3) Marching Cubes
    verts, faces, _, _ = measure.marching_cubes(
        mask.astype(np.uint8), level=0.5, spacing=spacing[::-1]  # (dx, dy, dz)
    )

    num_vertices = int(verts.shape[0])
    num_caras = int(faces.shape[0])

    # 4) Escribir STL
    out_dir_abs = _models_dir(session_id)
    ts = int(time.time())
    stl_filename = f"{ts}_seg3d_{seg3d_id}.stl"
    stl_abs_path = os.path.join(out_dir_abs, stl_filename)
    _write_binary_stl(stl_abs_path, verts, faces, name=b"dicom_3d_mesh")
    file_size_bytes = int(os.path.getsize(stl_abs_path))

    # Ruta pública
    stl_pub = f"{_public_models_dir(session_id)}/{stl_filename}"

    # 5) Guardar en DB (incluyendo file_size_bytes)
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
            session_id,
            int(user_id),
            seg3d_id,
            stl_pub,
            num_vertices,
            num_caras,
            file_size_bytes,
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
        "num_caras": num_caras,
        "file_size_bytes": file_size_bytes,
        "seg3d_id": seg3d_id,
        "created_at": created_at.isoformat() if created_at else None,
    }


def listar_modelos3d(session_id: str, user_id: int) -> list:
    """
    Lista modelos STL ya generados para una session_id y user_id.
    """
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


def borrar_modelo3d(modelo_id: int, user_id: int) -> bool:
    """
    Borra el registro y el archivo STL del disco si existe.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT session_id, path_stl FROM modelo3d WHERE id = %s AND user_id = %s",
        (modelo_id, user_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return False

    session_id, path_pub = row
    # Borrar registro
    cur.execute(
        "DELETE FROM modelo3d WHERE id = %s AND user_id = %s", (modelo_id, user_id)
    )
    conn.commit()
    cur.close()
    conn.close()

    # Borrar archivo
    if path_pub and path_pub.startswith("/static/"):
        rel = path_pub[len("/static/") :]  # models/<session>/file.stl
        abs_path = os.path.abspath(os.path.join("api", "static", rel))
        if os.path.isfile(abs_path):
            try:
                os.remove(abs_path)
            except Exception:
                pass

    # Si la carpeta queda vacía, opcional: eliminarla
    try:
        dir_abs = _models_dir(session_id)
        if os.path.isdir(dir_abs) and not os.listdir(dir_abs):
            os.rmdir(dir_abs)
    except Exception:
        pass

    return True

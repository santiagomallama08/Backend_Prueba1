# api/services/historial_services.py
import os
import re
import shutil
from typing import List, Dict
from config.db_config import get_connection


def extraer_session_id(ruta: str) -> str:
    """Extrae el session_id desde la ruta del archivo usando regex."""
    match = re.search(r"series[\\/](.*?)[\\/]", ruta)
    return match.group(1) if match else None


def contar_segmentaciones_por_session(conn, session_id: str, user_id: int) -> int:
    cur = conn.cursor()

    # Segmentaciones 2D (filtradas por usuario)
    cur.execute(
        """
        SELECT COUNT(*)
        FROM protesisdimension pd
        JOIN archivodicom ad ON ad.archivodicomid = pd.archivodicomid
        WHERE ad.rutaarchivo LIKE %s
          AND ad.user_id = %s
        """,
        (f"%{session_id}%", user_id),
    )
    count_2d = cur.fetchone()[0]

    # Segmentaciones 3D (filtradas por usuario)
    cur.execute(
        """
        SELECT COUNT(*)
        FROM segmentacion3d s3d
        WHERE s3d.session_id = %s
          AND s3d.user_id = %s
        """,
        (session_id, user_id),
    )
    count_3d = cur.fetchone()[0]

    cur.close()
    return count_2d + count_3d


def obtener_historial_archivos(user_id: int) -> List[Dict]:
    """Obtiene las series únicas de DICOM registradas en la base de datos."""
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT archivodicomid, nombrearchivo, rutaarchivo, fechacarga, sistemaid
        FROM archivodicom
        WHERE user_id = %s
        ORDER BY fechacarga DESC
    """
    cursor.execute(query, (user_id,))
    rows = cursor.fetchall()

    series_dict = {}

    for row in rows:
        ruta_relativa = row[2]
        ruta_absoluta = os.path.abspath(ruta_relativa)

        if not os.path.exists(ruta_absoluta):
            continue

        session_id = extraer_session_id(ruta_relativa)
        if not session_id:
            continue

        # Solo guardar una entrada por session_id
        if session_id not in series_dict:
            seg_count = contar_segmentaciones_por_session(conn, session_id, user_id)

            series_dict[session_id] = {
                "archivodicomid": row[0],
                "nombrearchivo": session_id,  # se muestra el session_id como nombre visible
                "rutaarchivo": row[2],
                "fechacarga": row[3],
                "sistemaid": row[4],
                "session_id": session_id,
                "has_segmentations": seg_count > 0,
                "seg_count": seg_count,
            }

    cursor.close()
    conn.close()
    return list(series_dict.values())


def eliminar_serie_por_session_id(session_id: str, user_id: int) -> None:
    """Elimina una serie completa: registros DICOM, imágenes y segmentaciones."""
    conn = get_connection()
    cursor = conn.cursor()

    # ❗ Bloqueo si hay segmentaciones
    seg_count = contar_segmentaciones_por_session(conn, session_id, user_id)
    if seg_count > 0:
        cursor.close()
        conn.close()
        raise ValueError("SERIE_CON_SEGMENTACIONES")

    # 1. Eliminar registros de la base de datos SOLO del usuario
    cursor.execute(
        "DELETE FROM archivodicom WHERE rutaarchivo LIKE %s AND user_id = %s",
        [f"%{session_id}%", user_id],
    )
    conn.commit()

    # 2. Eliminar la carpeta de imágenes y mapping
    ruta_series = os.path.abspath(f"api/static/series/{session_id}")
    if os.path.isdir(ruta_series):
        shutil.rmtree(ruta_series)

    # 3. Eliminar segmentaciones asociadas (si existen en disco)
    ruta_segmentaciones = os.path.abspath(f"api/static/segmentations/{session_id}")
    if os.path.isdir(ruta_segmentaciones):
        shutil.rmtree(ruta_segmentaciones)

    cursor.close()
    conn.close()


def _basename_sin_ext(ruta: str) -> str:
    return os.path.splitext(os.path.basename(ruta))[0]


def listar_segmentaciones_por_session_id(session_id: str, user_id: int) -> List[Dict]:
    """
    Lista segmentaciones (ProtesisDimension) asociadas a los DICOM cuya ruta contenga el session_id.
    Devuelve métricas + archivodicomid + (si existe) la ruta pública de la máscara.
    Busca máscaras en api/static/segmentations (sin subcarpetas por session).
    Filtrado por user_id para aislar datos por usuario.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT pd.archivodicomid,
               pd.altura, pd.volumen, pd.longitud, pd.ancho, pd.tipoprotesis, pd.unidad,
               ad.rutaarchivo
        FROM protesisdimension pd
        JOIN archivodicom ad ON ad.archivodicomid = pd.archivodicomid
        WHERE ad.rutaarchivo LIKE %s
          AND ad.user_id = %s
          AND pd.user_id = %s
        ORDER BY pd.archivodicomid
    """,
        [f"%{session_id}%", user_id, user_id],
    )

    rows = cur.fetchall()
    cur.close()
    conn.close()

    resultados = []
    segment_dir_abs = os.path.abspath("api/static/segmentations")

    for (
        archivodicomid,
        altura,
        volumen,
        longitud,
        ancho,
        tipoprotesis,
        unidad,
        ruta_dicom,
    ) in rows:
        base = _basename_sin_ext(ruta_dicom)  # p.ej. "image-00003"
        mask_filename = f"{base}_mask.png"
        mask_abs = os.path.join(segment_dir_abs, mask_filename)
        if os.path.isfile(mask_abs):
            mask_public = f"/static/segmentations/{mask_filename}"
        else:
            mask_public = None

        resultados.append(
            {
                "archivodicomid": archivodicomid,
                "altura": float(altura),
                "volumen": float(volumen),
                "longitud": float(longitud),
                "ancho": float(ancho),
                "tipoprotesis": tipoprotesis,
                "unidad": unidad,
                "mask_path": mask_public,
            }
        )

    return resultados


def eliminar_segmentacion_por_archivo(
    session_id: str, archivodicomid: int, user_id: int
) -> bool:
    """
    Elimina la segmentación (fila en ProtesisDimension) para un archivodicomid
    y borra la máscara en disco si existe. Las máscaras están en api/static/segmentations/
    Valida que la segmentación y el dicom pertenezcan al usuario y a la serie.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Validar pertenencia del DICOM a user y a session
        cur.execute(
            """
            SELECT rutaarchivo FROM archivodicom
            WHERE archivodicomid = %s
              AND user_id = %s
              AND rutaarchivo LIKE %s
        """,
            [archivodicomid, user_id, f"%{session_id}%"],
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return False

        ruta_dicom = row[0]
        base = _basename_sin_ext(ruta_dicom)
        mask_filename = f"{base}_mask.png"
        mask_abs = os.path.abspath(f"api/static/segmentations/{mask_filename}")

        # Borrar fila en ProtesisDimension SOLO del usuario
        cur.execute(
            """
            DELETE FROM protesisdimension
            WHERE archivodicomid = %s
              AND user_id = %s
        """,
            [archivodicomid, user_id],
        )
        conn.commit()

        # Intentar borrar archivo (si existe)
        if os.path.isfile(mask_abs):
            try:
                os.remove(mask_abs)
            except Exception:
                pass

        cur.close()
        conn.close()
        return True

    except Exception:
        cur.close()
        conn.close()
        return False

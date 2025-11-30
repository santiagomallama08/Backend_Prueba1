import os
import re
import shutil
from typing import List, Dict
from config.db_config import get_connection

# Importamos las rutas persistentes DESDE config.paths
from config.paths import SERIES_DIR, BASE_STATIC_DIR, SEGMENTATIONS_2D_DIR

# Directorio de máscaras 2D persistente
SEGMENTATIONS_DIR = SEGMENTATIONS_2D_DIR
SEGMENTATIONS_DIR.mkdir(exist_ok=True)


def extraer_session_id(ruta: str) -> str:
    """Extrae el session_id de rutas tipo /data/static/series/<session_id>/"""
    match = re.search(r"series[\\/](.*?)[\\/]", ruta)
    return match.group(1) if match else None


def contar_segmentaciones_por_session(conn, session_id: str, user_id: int) -> int:
    cur = conn.cursor()

    # Segmentaciones 2D
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

    # Segmentaciones 3D
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
    """Lista las series guardadas en archivodicom y en el volumen persistente."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT archivodicomid, nombrearchivo, rutaarchivo, fechacarga, sistemaid
        FROM archivodicom
        WHERE user_id = %s
        ORDER BY fechacarga DESC
        """,
        (user_id,),
    )
    rows = cursor.fetchall()

    series_dict = {}

    for row in rows:
        ruta_relativa = row[2]
        ruta_absoluta = ruta_relativa

        if not os.path.exists(ruta_absoluta):
            continue

        session_id = extraer_session_id(ruta_relativa)
        if not session_id:
            continue

        if session_id not in series_dict:
            seg_count = contar_segmentaciones_por_session(conn, session_id, user_id)

            series_dict[session_id] = {
                "archivodicomid": row[0],
                "nombrearchivo": session_id,
                "rutaarchivo": ruta_relativa,
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
    """Elimina una serie completa de /data/static."""
    conn = get_connection()
    cursor = conn.cursor()

    seg_count = contar_segmentaciones_por_session(conn, session_id, user_id)
    if seg_count > 0:
        cursor.close()
        conn.close()
        raise ValueError("SERIE_CON_SEGMENTACIONES")

    cursor.execute(
        "DELETE FROM archivodicom WHERE rutaarchivo LIKE %s AND user_id = %s",
        [f"%{session_id}%", user_id],
    )
    conn.commit()

    ruta_series = SERIES_DIR / session_id
    if ruta_series.is_dir():
        shutil.rmtree(ruta_series)

    ruta_masks = SEGMENTATIONS_DIR / session_id
    if ruta_masks.is_dir():
        shutil.rmtree(ruta_masks)

    cursor.close()
    conn.close()


def _basename_sin_ext(ruta: str) -> str:
    return os.path.splitext(os.path.basename(ruta))[0]


def listar_segmentaciones_por_session_id(session_id: str, user_id: int) -> List[Dict]:
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

        base = _basename_sin_ext(ruta_dicom)
        mask_filename = f"{base}_mask.png"

        mask_abs = SEGMENTATIONS_DIR / session_id / mask_filename

        if mask_abs.is_file():
            mask_public = f"/static/segmentations/{session_id}/{mask_filename}"
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


def eliminar_segmentacion_por_archivo(session_id: str, archivodicomid: int, user_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    try:
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

        mask_abs = SEGMENTATIONS_DIR / session_id / mask_filename

        cur.execute(
            """
            DELETE FROM protesisdimension
            WHERE archivodicomid = %s
              AND user_id = %s
            """,
            [archivodicomid, user_id],
        )
        conn.commit()

        if mask_abs.is_file():
            try:
                mask_abs.unlink()
            except Exception:
                pass

        cur.close()
        conn.close()
        return True

    except Exception:
        cur.close()
        conn.close()
        return False

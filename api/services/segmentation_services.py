import datetime
import os
import numpy as np
import pydicom
from skimage import measure, morphology, io
from skimage.measure import regionprops

from config.db_config import get_connection

# 📌 Importar la carpeta persistente desde main.py
from api.main import SEGMENTATIONS_2D_DIR   # /data/static/segmentations


def segmentar_dicom(
    dicom_path: str,
    archivodicomid: int,
    user_id: int,
    session_id: str = None
) -> dict:
    """
    Segmentación 2D sobre un archivo DICOM individual.
    Guarda la máscara en /data/static/segmentations/<session_id>/
    """

    # ========== 1) Determinar session_id a partir de la ruta ==========
    if session_id is None:
        # extraer el session_id desde ruta tipo .../series/<session_id>/archivo.dcm
        parts = dicom_path.replace("\\", "/").split("/")
        if "series" in parts:
            idx = parts.index("series")
            session_id = parts[idx + 1]
        else:
            session_id = "default"

    # ========== 2) Carpeta persistente para almacenar la máscara ==========
    output_dir = SEGMENTATIONS_2D_DIR / session_id
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # ========== 3) Leer el DICOM ==========
        ds = pydicom.dcmread(dicom_path)
        imagen = ds.pixel_array.astype(np.int16)

        # ========== 4) Segmentación ==========
        umbral = 400
        mascara = imagen > umbral
        mascara = morphology.remove_small_objects(mascara, min_size=500)

        etiquetas = measure.label(mascara)
        props = regionprops(etiquetas)

        if props:
            lbl = max(props, key=lambda r: r.area).label
            segmento = etiquetas == lbl
        else:
            segmento = np.zeros_like(imagen)

        binaria = segmento.astype(np.uint8) * 255

        # ========== 5) Guardar máscara en disco (persistente) ==========
        base = os.path.splitext(os.path.basename(dicom_path))[0]
        rel_filename = f"{base}_mask.png"
        absolute_mask_path = output_dir / rel_filename

        io.imsave(str(absolute_mask_path), binaria)

        # ========== 6) Calcular medidas ==========
        px_y, px_x = ds.PixelSpacing
        slice_thk = getattr(ds, "SliceThickness", 1.0)

        if props:
            r = max(props, key=lambda r: r.area)
            minr, minc, maxr, maxc = r.bbox
            largo_px = maxr - minr
            ancho_px = maxc - minc
            area_px = r.area
            perim_px = r.perimeter

            dimensiones = {
                "Longitud (mm)": round(largo_px * px_y, 2),
                "Ancho (mm)": round(ancho_px * px_x, 2),
                "Altura (mm)": round(slice_thk, 2),
                "Área (mm²)": round(area_px * px_x * px_y, 2),
                "Perímetro (px)": round(perim_px, 2),
                "Volumen (mm³)": round(area_px * px_x * px_y * slice_thk, 2),
            }

            # Guardar en BD
            datos_bd = {
                "archivodicomid": archivodicomid,
                "altura": dimensiones["Altura (mm)"],
                "volumen": dimensiones["Volumen (mm³)"],
                "longitud": dimensiones["Longitud (mm)"],
                "ancho": dimensiones["Ancho (mm)"],
                "tipoprotesis": "Cráneo",
                "unidad": "mm³",
                "user_id": user_id,
            }
            guardar_protesis_dimension(datos_bd)

        else:
            dimensiones = {"error": "No se detectó región válida."}

        # ========== 7) Ruta pública (para frontend) ==========
        public_mask_path = f"/static/segmentations/{session_id}/{rel_filename}"

        return {
            "mensaje": "Segmentación exitosa",
            "mask_path": public_mask_path,
            "dimensiones": dimensiones,
        }

    except Exception as e:
        return {"error": str(e)}


def guardar_protesis_dimension(data: dict) -> bool:
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO ProtesisDimension
              (archivodicomid, altura, volumen, longitud, ancho, tipoprotesis, unidad, user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                int(data["archivodicomid"]),
                float(data["altura"]),
                float(data["volumen"]),
                float(data["longitud"]),
                float(data["ancho"]),
                str(data["tipoprotesis"]),
                str(data["unidad"]),
                int(data["user_id"]),
            ),
        )

        conn.commit()
        cursor.close()
        conn.close()
        return True

    except Exception as e:
        print("❌ Error al guardar dimensiones:", e)
        return False


def get_or_create_archivo_dicom(
    nombrearchivo: str, rutaarchivo: str, sistemaid: int = 1, user_id: int = None
) -> int:
    """
    Busca un archivo DICOM por nombre y ruta. Si no existe, lo inserta.
    Retorna el archivodicomid.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT archivodicomid FROM ArchivoDicom
        WHERE nombrearchivo = %s AND rutaarchivo = %s AND user_id = %s
        """,
        (nombrearchivo, rutaarchivo, user_id),
    )
    resultado = cursor.fetchone()

    if resultado:
        archivo_id = resultado[0]
    else:
        cursor.execute(
            """
            INSERT INTO ArchivoDicom (fechacarga, sistemaid, nombrearchivo, rutaarchivo, user_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING archivodicomid
            """,
            (datetime.date.today(), sistemaid, nombrearchivo, rutaarchivo, user_id),
        )
        archivo_id = cursor.fetchone()[0]
        conn.commit()

    cursor.close()
    conn.close()
    return archivo_id

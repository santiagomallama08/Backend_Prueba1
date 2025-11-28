# api/services/segmentation_services.py
import datetime
import os
import numpy as np
import pydicom
from skimage import measure, morphology, io
from skimage.measure import regionprops
from uuid import uuid4

from config.db_config import get_connection


def segmentar_dicom(
    dicom_path: str, archivodicomid: int, user_id: int, output_dir: str = None
) -> dict:

    # 1) Definir output_dir absoluto apuntando a api/static/segmentations
    if output_dir is None:
        output_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "static", "segmentations")
        )

    try:
        # 2) Asegurarse de que exista
        os.makedirs(output_dir, exist_ok=True)

        # 3) Leer DICOM y segmentar...
        ds = pydicom.dcmread(dicom_path)
        imagen = ds.pixel_array.astype(np.int16)
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

        # 4) Guardar máscara en disco
        base = os.path.splitext(os.path.basename(dicom_path))[0]
        rel_filename = f"{base}_mask.png"
        absolute_mask_path = os.path.join(output_dir, rel_filename)
        io.imsave(absolute_mask_path, binaria)

        # 5) Calcular dimensiones
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

            # Guardar en base de datos
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

        # 6) Construir y devolver la ruta pública relativa (para frontend)
        public_mask_path = f"/static/segmentations/{rel_filename}"

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

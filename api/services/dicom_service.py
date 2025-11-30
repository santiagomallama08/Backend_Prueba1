import json
import os
import io
import uuid
import zipfile
from typing import List
from skimage import exposure
import pydicom
from PIL import Image
import numpy as np

from .segmentation_services import get_or_create_archivo_dicom

# --- 🎯 VARIABLE DE RUTA PERSISTENTE (Misma definición que en el router) ---
# Usamos una variable de entorno que debes configurar en Railway. 
PERSISTENT_STORAGE_BASE = os.environ.get("RAILWAY_STORAGE_PATH", os.path.join("api", "static"))
# ----------------------------------------------------------------------------------

def convert_dicom_zip_to_png_paths(zip_file: bytes, user_id: int) -> dict:
    """
    Convierte un archivo ZIP con múltiples DICOMs en imágenes PNG y genera mapping.json
    Guardando todo en el volumen persistente definido por PERSISTENT_STORAGE_BASE.
    """
    # Crear carpeta única por sesión en la base de almacenamiento persistente
    session_id = str(uuid.uuid4())
    # --- 🎯 CAMBIO 1: output_dir ahora usa la ruta persistente ---
    output_dir = os.path.join(PERSISTENT_STORAGE_BASE, "series", session_id)
    os.makedirs(output_dir, exist_ok=True)

    dicom_mapping = {}
    image_paths = []

    with zipfile.ZipFile(io.BytesIO(zip_file)) as archive:
        # Buscar archivos DICOM (extensiones comunes)
        dcm_files = [f for f in archive.namelist() if f.lower().endswith((".dcm", ""))]
        if not dcm_files:
            # Limpiar directorio si falla al principio
            os.rmdir(output_dir)
            raise ValueError("No se encontraron archivos DICOM en el ZIP.")

        for idx, dicom_name in enumerate(dcm_files):
            try:
                # Extraer archivo DICOM
                with archive.open(dicom_name) as file:
                    dicom_bytes = file.read()

                # --- 🎯 CAMBIO 2: Guardar el DICOM en la ruta persistente ---
                dicom_output_path = os.path.join(output_dir, os.path.basename(dicom_name))
                os.makedirs(os.path.dirname(dicom_output_path), exist_ok=True)
                with open(dicom_output_path, "wb") as f:
                    f.write(dicom_bytes)

                # Leer DICOM (el resto del procesamiento es igual)
                ds = pydicom.dcmread(io.BytesIO(dicom_bytes), force=True)
                if "PixelData" not in ds:
                    print(f"⚠️ Archivo sin datos de imagen: {dicom_name}")
                    # Borrar el archivo DICOM que acabamos de guardar
                    os.remove(dicom_output_path)
                    continue

                # === 4️⃣ Generar imagen PNG de vista previa ===
                # ... (Procesamiento de imagen)
                
                # Guardar como PNG
                png_filename = f"image_{idx}.png"
                # --- 🎯 CAMBIO 3: Guardar el PNG en la ruta persistente ---
                png_path = os.path.join(output_dir, png_filename)
                im = Image.fromarray(image).convert("L")
                im.save(png_path)

                # === 5️⃣ Registrar archivo en la base de datos ===
                archivo_id = get_or_create_archivo_dicom(
                    nombrearchivo=os.path.basename(dicom_name),
                    # --- 🎯 CAMBIO 4: Guardar la RUTA PERSISTENTE en la base de datos ---
                    rutaarchivo=dicom_output_path, 
                    sistemaid=1,
                    user_id=user_id,
                )

                # === 6️⃣ Agregar al mapping ===
                dicom_mapping[png_filename] = {
                    "dicom_name": os.path.basename(dicom_name),
                    "archivodicomid": archivo_id,
                }

                # La ruta de retorno al frontend sigue siendo /static/
                image_paths.append(f"/static/series/{session_id}/{png_filename}")

            except Exception as e:
                print(f"⚠️ Error procesando {dicom_name}: {e}")
                continue

    # Validar resultados
    if not image_paths:
        # Limpiar directorio si no se pudo procesar nada
        os.rmdir(output_dir)
        raise ValueError("No se pudieron procesar archivos DICOM válidos.")

    # Guardar mapping.json
    # --- 🎯 CAMBIO 5: Guardar el mapping.json en la ruta persistente ---
    mapping_path = os.path.join(output_dir, "mapping.json")
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(dicom_mapping, f, ensure_ascii=False, indent=2)

    # Retornar resultado
    return {
        "message": "ZIP procesado correctamente",
        "session_id": session_id,
        "image_series": image_paths,
        "mapping_url": f"/static/series/{session_id}/mapping.json",
    }
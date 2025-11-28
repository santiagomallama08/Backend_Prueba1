# api/services/dicom_service.py
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


def convert_dicom_zip_to_png_paths(zip_file: bytes, user_id: int) -> dict:
    """
    Convierte un archivo ZIP con múltiples DICOMs en imágenes PNG y genera mapping.json
    """
    # Crear carpeta única por sesión
    session_id = str(uuid.uuid4())
    output_dir = os.path.join("api", "static", "series", session_id)
    os.makedirs(output_dir, exist_ok=True)

    dicom_mapping = {}
    image_paths = []

    with zipfile.ZipFile(io.BytesIO(zip_file)) as archive:
        # Buscar archivos DICOM (extensiones comunes)
        dcm_files = [f for f in archive.namelist() if f.lower().endswith((".dcm", ""))]
        if not dcm_files:
            raise ValueError("No se encontraron archivos DICOM en el ZIP.")

        for idx, dicom_name in enumerate(dcm_files):
            try:
                # Extraer archivo DICOM
                with archive.open(dicom_name) as file:
                    dicom_bytes = file.read()

                dicom_output_path = os.path.join(output_dir, os.path.basename(dicom_name))
                os.makedirs(os.path.dirname(dicom_output_path), exist_ok=True)
                with open(dicom_output_path, "wb") as f:
                    f.write(dicom_bytes)

                # Leer DICOM
                ds = pydicom.dcmread(io.BytesIO(dicom_bytes), force=True)
                if "PixelData" not in ds:
                    print(f"⚠️ Archivo sin datos de imagen: {dicom_name}")
                    continue

                # === 4️⃣ Generar imagen PNG de vista previa ===
                image = ds.pixel_array.astype(np.float32)

                # Normaliza al rango [0, 1]
                if np.max(image) > 1:
                    image = (image - np.min(image)) / (np.max(image) - np.min(image) + 1e-6)

                # Aplica CLAHE (ecualización adaptativa)
                try:
                    image = exposure.equalize_adapthist(image)
                except Exception:
                    # Si falla, recorta valores
                    image = np.clip(image, 0, 1)

                # Convierte a 8 bits (0-255)
                image = (image * 255).astype("uint8")
                im = Image.fromarray(image).convert("L")

                # Guardar como PNG
                png_filename = f"image_{idx}.png"
                png_path = os.path.join(output_dir, png_filename)
                im.save(png_path)

                # === 5️⃣ Registrar archivo en la base de datos ===
                archivo_id = get_or_create_archivo_dicom(
                    nombrearchivo=os.path.basename(dicom_name),
                    rutaarchivo=dicom_output_path,
                    sistemaid=1,
                    user_id=user_id,
                )

                # === 6️⃣ Agregar al mapping ===
                dicom_mapping[png_filename] = {
                    "dicom_name": os.path.basename(dicom_name),
                    "archivodicomid": archivo_id,
                }

                image_paths.append(f"/static/series/{session_id}/{png_filename}")

            except Exception as e:
                print(f"⚠️ Error procesando {dicom_name}: {e}")
                continue

    # Validar resultados
    if not image_paths:
        raise ValueError("No se pudieron procesar archivos DICOM válidos.")

    # Guardar mapping.json
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

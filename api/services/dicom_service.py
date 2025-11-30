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

# Importar la ruta persistente del volumen
from main import SERIES_DIR


def convert_dicom_zip_to_png_paths(zip_file: bytes, user_id: int) -> dict:
    """
    Convierte un archivo ZIP con múltiples DICOMs en imágenes PNG
    y genera mapping.json dentro del volumen persistente.
    """

    # 1️⃣ Crear carpeta única por sesión dentro del volumen /data/static/series
    session_id = str(uuid.uuid4())
    output_dir = SERIES_DIR / session_id
    output_dir.mkdir(parents=True, exist_ok=True)

    dicom_mapping = {}
    image_paths = []

    # 2️⃣ Leer archivo ZIP
    with zipfile.ZipFile(io.BytesIO(zip_file)) as archive:

        # Buscar todos los DICOM
        dcm_files = [f for f in archive.namelist() if f.lower().endswith((".dcm", ""))]
        if not dcm_files:
            raise ValueError("No se encontraron archivos DICOM en el ZIP.")

        # 3️⃣ Procesar cada archivo DICOM
        for idx, dicom_name in enumerate(dcm_files):
            try:
                with archive.open(dicom_name) as file:
                    dicom_bytes = file.read()

                # Ruta DICOM dentro del volumen persistente
                dicom_output_path = output_dir / os.path.basename(dicom_name)

                # Guardar archivo DICOM
                with open(dicom_output_path, "wb") as f:
                    f.write(dicom_bytes)

                # Leer DICOM
                ds = pydicom.dcmread(io.BytesIO(dicom_bytes), force=True)
                if "PixelData" not in ds:
                    print(f"⚠️ Archivo sin datos de imagen: {dicom_name}")
                    continue

                # 4️⃣ Convertir a imagen PNG
                image = ds.pixel_array.astype(np.float32)

                # Normalizar imagen
                if np.max(image) > 1:
                    image = (image - np.min(image)) / (np.max(image) - np.min(image) + 1e-6)

                # Aplicar CLAHE
                try:
                    image = exposure.equalize_adapthist(image)
                except Exception:
                    image = np.clip(image, 0, 1)

                # Convertir a 8 bits
                image = (image * 255).astype("uint8")
                im = Image.fromarray(image).convert("L")

                # Guardar PNG en el volumen persistente
                png_filename = f"image_{idx}.png"
                png_path = output_dir / png_filename
                im.save(png_path)

                # 5️⃣ Registrar archivo en DB
                archivo_id = get_or_create_archivo_dicom(
                    nombrearchivo=os.path.basename(dicom_name),
                    rutaarchivo=str(dicom_output_path),
                    sistemaid=1,
                    user_id=user_id,
                )

                # 6️⃣ Agregar al mapping
                dicom_mapping[png_filename] = {
                    "dicom_name": os.path.basename(dicom_name),
                    "archivodicomid": archivo_id,
                }

                # 7️⃣ Guardar rutas públicas correctas
                image_paths.append(f"/static/series/{session_id}/{png_filename}")

            except Exception as e:
                print(f"⚠️ Error procesando {dicom_name}: {e}")
                continue

    # Validar resultados
    if not image_paths:
        raise ValueError("No se pudieron procesar archivos DICOM válidos.")

    # 8️⃣ Guardar mapping.json en el volumen persistente
    mapping_path = output_dir / "mapping.json"
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(dicom_mapping, f, ensure_ascii=False, indent=2)

    # 9️⃣ Retornar información
    return {
        "message": "ZIP procesado correctamente",
        "session_id": session_id,
        "image_series": image_paths,
        "mapping_url": f"/static/series/{session_id}/mapping.json",
    }

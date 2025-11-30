import json
import os
import io
import uuid
import zipfile
import numpy as np
from skimage import exposure
from PIL import Image
import pydicom

from .segmentation_services import get_or_create_archivo_dicom


def convert_dicom_zip_to_png_paths(
    zip_file: bytes,
    user_id: int,
    base_output_dir: str | os.PathLike = "api/static/series"
) -> dict:
    """
    Convierte un ZIP con DICOM y genera imágenes + mapping.json dentro del volumen.
    """

    # Crear carpeta única por sesión dentro del volumen
    session_id = str(uuid.uuid4())
    output_dir = os.path.join(base_output_dir, session_id)
    os.makedirs(output_dir, exist_ok=True)

    dicom_mapping = {}
    image_paths = []

    with zipfile.ZipFile(io.BytesIO(zip_file)) as archive:

        dcm_files = [f for f in archive.namelist() if f.lower().endswith((".dcm", ""))]
        if not dcm_files:
            raise ValueError("No se encontraron archivos DICOM en el ZIP.")

        for idx, dicom_name in enumerate(dcm_files):

            try:
                with archive.open(dicom_name) as file:
                    dicom_bytes = file.read()

                dicom_output_path = os.path.join(output_dir, os.path.basename(dicom_name))

                with open(dicom_output_path, "wb") as f:
                    f.write(dicom_bytes)

                ds = pydicom.dcmread(io.BytesIO(dicom_bytes), force=True)
                if "PixelData" not in ds:
                    continue

                image = ds.pixel_array.astype(np.float32)

                if np.max(image) > 1:
                    image = (image - np.min(image)) / (np.max(image) - np.min(image) + 1e-6)

                try:
                    image = exposure.equalize_adapthist(image)
                except:
                    image = np.clip(image, 0, 1)

                image = (image * 255).astype("uint8")
                im = Image.fromarray(image).convert("L")

                png_filename = f"image_{idx}.png"
                png_path = os.path.join(output_dir, png_filename)
                im.save(png_path)

                archivo_id = get_or_create_archivo_dicom(
                    nombrearchivo=os.path.basename(dicom_name),
                    rutaarchivo=dicom_output_path,
                    sistemaid=1,
                    user_id=user_id,
                )

                dicom_mapping[png_filename] = {
                    "dicom_name": os.path.basename(dicom_name),
                    "archivodicomid": archivo_id,
                }

                # RUTA PUBLICA
                image_paths.append(f"/static/series/{session_id}/{png_filename}")

            except Exception as e:
                print("⛔ Error procesando DICOM:", dicom_name, e)
                continue

    # mapping.json
    mapping_path = os.path.join(output_dir, "mapping.json")
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(dicom_mapping, f, ensure_ascii=False, indent=2)

    return {
        "message": "ZIP procesado correctamente",
        "session_id": session_id,
        "image_series": image_paths,
        "mapping_url": f"/static/series/{session_id}/mapping.json",
    }

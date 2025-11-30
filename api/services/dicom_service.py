# api/services/dicom_service.py
import json
import os
import io
import uuid
import zipfile
from skimage import exposure
import pydicom
from PIL import Image
import numpy as np
from pathlib import Path

from .segmentation_services import get_or_create_archivo_dicom


def convert_dicom_zip_to_png_paths(zip_file: bytes, user_id: int, base_dir: Path) -> dict:
    """
    Convierte ZIP → DICOMs → PNGs y mapping.json usando SIEMPRE el volumen.
    """
    session_id = str(uuid.uuid4())

    # 🔥 RUTA FINAL en el volumen real
    output_dir = base_dir / session_id
    output_dir.mkdir(parents=True, exist_ok=True)

    dicom_mapping = {}
    image_paths = []

    with zipfile.ZipFile(io.BytesIO(zip_file)) as archive:
        dcm_files = [f for f in archive.namelist() if f.lower().endswith(".dcm")]

        if not dcm_files:
            raise ValueError("No se encontraron DICOM en el ZIP.")

        for idx, dicom_name in enumerate(dcm_files):
            try:
                dicom_bytes = archive.read(dicom_name)

                dicom_output_path = output_dir / os.path.basename(dicom_name)
                with open(dicom_output_path, "wb") as f:
                    f.write(dicom_bytes)

                ds = pydicom.dcmread(io.BytesIO(dicom_bytes), force=True)
                if "PixelData" not in ds:
                    continue

                img = ds.pixel_array.astype(np.float32)
                img = (img - np.min(img)) / (np.max(img) - np.min(img) + 1e-6)
                img = exposure.equalize_adapthist(img)
                img = (img * 255).astype(np.uint8)

                im = Image.fromarray(img).convert("L")

                png_name = f"image_{idx}.png"
                png_path = output_dir / png_name
                im.save(png_path)

                archivo_id = get_or_create_archivo_dicom(
                    nombrearchivo=os.path.basename(dicom_name),
                    rutaarchivo=str(dicom_output_path),
                    sistemaid=1,
                    user_id=user_id,
                )

                dicom_mapping[png_name] = {
                    "dicom_name": os.path.basename(dicom_name),
                    "archivodicomid": archivo_id,
                }

                # 🔥 Ruta pública INVARIABLE
                image_paths.append(f"/static/series/{session_id}/{png_name}")

            except Exception as e:
                print("Error:", e)

    if not image_paths:
        raise ValueError("No se pudieron procesar imágenes")

    # Guardar mapping.json en el volumen
    with open(output_dir / "mapping.json", "w", encoding="utf-8") as f:
        json.dump(dicom_mapping, f, indent=2, ensure_ascii=False)

    return {
        "message": "ZIP procesado correctamente",
        "session_id": session_id,
        "image_series": image_paths,
        "mapping_url": f"/static/series/{session_id}/mapping.json",
    }

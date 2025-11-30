import json
import os
import io
import uuid
import zipfile
import shutil
from typing import List
from skimage import exposure
import pydicom
from PIL import Image
import numpy as np

from .segmentation_services import get_or_create_archivo_dicom

# --- VARIABLE DE RUTA PERSISTENTE (USADA POR RAILWAY) ---
# Usamos STORAGE_BASE_PATH, que es la variable definida en main.py y en Railway.
# El valor es la ruta física completa del volumen.
PERSISTENT_STORAGE_BASE = os.environ.get(
    "STORAGE_BASE_PATH", 
    os.path.join("api", "static", "series") # Valor local por defecto
)
# --------------------------------------------------------

def convert_dicom_zip_to_png_paths(zip_file: bytes, user_id: int) -> dict:
    """
    Convierte un archivo ZIP con múltiples DICOMs en imágenes PNG y genera mapping.json
    Guardando todo en el volumen persistente.
    """
    session_id = str(uuid.uuid4())
    
    # 🔴 CORRECCIÓN CLAVE: output_dir debe ser directamente la ruta del volumen + session_id
    # Ya que el main.py monta /static/series -> [PERSISTENT_STORAGE_BASE]
    # No necesitamos añadir "/series" aquí, ya que STORAGE_BASE_PATH ya es la carpeta raíz de las series.
    output_dir = os.path.join(PERSISTENT_STORAGE_BASE, session_id)
    os.makedirs(output_dir, exist_ok=True)

    dicom_mapping = {}
    image_paths = []

    try:
        # ... (Resto del código es correcto, guarda los archivos directamente en output_dir)
        
        # [Se omite el cuerpo de la función para brevedad, solo se modifica la inicialización de output_dir]
        
        with zipfile.ZipFile(io.BytesIO(zip_file)) as archive:
            dcm_files = [f for f in archive.namelist() if f.lower().endswith((".dcm", ""))]
            
            if not dcm_files:
                shutil.rmtree(output_dir)
                raise ValueError("No se encontraron archivos DICOM en el ZIP.")

            for idx, dicom_name_in_zip in enumerate(dcm_files):
                dicom_output_path = None

                try:
                    # Normalizar el nombre de archivo, solo tomando el componente final
                    safe_dicom_filename = os.path.basename(dicom_name_in_zip)
                    
                    if not safe_dicom_filename:
                         continue # Saltar si el nombre es solo un directorio

                    # 1. Extracción y Guardado del DICOM
                    with archive.open(dicom_name_in_zip) as file:
                        dicom_bytes = file.read()

                    dicom_output_path = os.path.join(output_dir, safe_dicom_filename)
                    
                    with open(dicom_output_path, "wb") as f:
                        f.write(dicom_bytes)

                    # 2. Lectura y Validación (omitiendo por brevedad)
                    ds = pydicom.dcmread(io.BytesIO(dicom_bytes), force=True)
                    
                    if "PixelData" not in ds:
                        print(f"⚠️ Archivo sin datos de imagen: {dicom_name_in_zip}")
                        os.remove(dicom_output_path)
                        continue
                    
                    # 3. Procesamiento de Imagen (omitiendo por brevedad)
                    image = ds.pixel_array.astype(np.float32)

                    if np.max(image) > 1:
                        image = (image - np.min(image)) / (np.max(image) - np.min(image) + 1e-6)

                    try:
                        image = exposure.equalize_adapthist(image)
                    except Exception:
                        image = np.clip(image, 0, 1)

                    image = (image * 255).astype("uint8")
                    im = Image.fromarray(image).convert("L")

                    # 4. Guardar como PNG
                    png_filename = f"image_{idx}.png"
                    png_path = os.path.join(output_dir, png_filename)
                    im.save(png_path)

                    # 5. Registrar archivo en la base de datos (omitiendo por brevedad)
                    archivo_id = get_or_create_archivo_dicom(
                        nombrearchivo=safe_dicom_filename,
                        rutaarchivo=dicom_output_path, 
                        sistemaid=1,
                        user_id=user_id,
                    )

                    # 6. Agregar al mapping
                    dicom_mapping[png_filename] = {
                        "dicom_name": safe_dicom_filename,
                        "archivodicomid": archivo_id,
                    }

                    image_paths.append(f"/static/series/{session_id}/{png_filename}")

                except Exception as e:
                    print(f"⚠️ Error procesando {dicom_name_in_zip}: {e}")
                    if dicom_output_path and os.path.isfile(dicom_output_path):
                        os.remove(dicom_output_path)
                    continue

        if not image_paths:
            shutil.rmtree(output_dir)
            raise ValueError("No se pudieron procesar archivos DICOM válidos.")

        mapping_path = os.path.join(output_dir, "mapping.json")
        with open(mapping_path, "w", encoding="utf-8") as f:
            json.dump(dicom_mapping, f, ensure_ascii=False, indent=2)

        return {
            "message": "ZIP procesado correctamente",
            "session_id": session_id,
            "image_series": image_paths,
            "mapping_url": f"/static/series/{session_id}/mapping.json",
        }
        
    except Exception as e:
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        raise e
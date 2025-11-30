import tempfile
from typing import Optional
import os
import json
from pathlib import Path

from fastapi import (
    APIRouter, Form, HTTPException, Path as FPath, UploadFile, File, Header, Query
)
from fastapi.responses import JSONResponse
import pydicom

# Asumo que estos imports son correctos
from ..services.segmentation3d_service import segmentar_serie_3d
from ..services.dicom_service import convert_dicom_zip_to_png_paths


router = APIRouter()

# --- 🎯 VARIABLE DE RUTA PERSISTENTE (CRÍTICA) ---
# Debe coincidir con el Mount Path: /api/static/series
# Usamos STORAGE_BASE_PATH, ya que RAILWAY_STORAGE_PATH no es la convención estándar.
PERSISTENT_STORAGE_BASE = os.environ.get(
    "STORAGE_BASE_PATH", 
    "/api/static/series" # Valor por defecto unificado (coincide con el volumen de Railway)
)
# ----------------------------------------------------------------------------------


@router.post("/upload-dicom")
async def upload_dicom(file: UploadFile = File(...)):
    """Procesa un solo archivo DICOM, guarda temporalmente, extrae metadatos y luego lo borra."""
    try:
        # Guardar temporalmente el archivo (no usa el volumen persistente, se borra inmediatamente)
        contents = await file.read()
        # Usar tempfile.gettempdir() asegura una ruta temporal del sistema operativo
        temp_path = os.path.join(tempfile.gettempdir(), f"temp_{file.filename}")
        with open(temp_path, "wb") as f:
            f.write(contents)

        # Leer el archivo con pydicom
        dicom = pydicom.dcmread(temp_path)

        # Extraer metadatos
        metadata = {
            "PatientID": dicom.get("PatientID", "N/A"),
            "StudyDate": dicom.get("StudyDate", "N/A"),
            "Modality": dicom.get("Modality", "N/A"),
            "Rows": dicom.get("Rows", "N/A"),
            "Columns": dicom.get("Columns", "N/A"),
            "NumberOfFrames": dicom.get("NumberOfFrames", "1"),
            "SOPInstanceUID": dicom.get("SOPInstanceUID", "N/A"),
        }

        # Borrar archivo temporal
        os.remove(temp_path)

        # Devolver metadatos
        return JSONResponse(
            content={
                "message": "Archivo DICOM subido y procesado exitosamente.",
                "metadata": metadata,
            }
        )

    except Exception as e:
        # Aquí también podemos borrar el archivo temporal si existe
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-dicom-series/")
async def upload_dicom_series(
    file: UploadFile = File(...),
    x_user_id: int = Header(..., alias="X-User-Id"),  
):
    """Sube un archivo ZIP con una serie DICOM y llama al servicio para procesarla."""
    if not file.filename.endswith(".zip"):
        raise HTTPException(
            status_code=400, detail="Debe subir un archivo .zip con archivos DICOM"
        )
    try:
        zip_bytes = await file.read()

        # convert_dicom_zip_to_png_paths ahora usará PERSISTENT_STORAGE_BASE
        image_paths = convert_dicom_zip_to_png_paths(zip_bytes, user_id=x_user_id)
        return JSONResponse(
            content={
                "message": f"{len(image_paths['image_series'])} imágenes convertidas correctamente.",
                "image_series": image_paths['image_series'],
                "session_id": image_paths['session_id'],
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/segmentar-dicom/")
async def segmentar_dicom_endpoint(file: UploadFile = File(...)):
    """Segmenta un DICOM individual (usa tempfile para no escribir en el volumen)."""
    # ... (El código de segmentar-dicom parece correcto y utiliza tempfile)
    try:
        # Guardar DICOM temporalmente (usa tempfile, no afecta el volumen)
        contents = await file.read()
        temp_dir = tempfile.mkdtemp()
        dicom_path = os.path.join(temp_dir, file.filename)

        with open(dicom_path, "wb") as f:
            f.write(contents)

        # Llamar servicio
        from ..services.segmentation_services import segmentar_dicom

        resultado = segmentar_dicom(dicom_path)

        return resultado

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Limpiar directorio temporal
        if 'temp_dir' in locals() and os.path.isdir(temp_dir):
             # os.rmdir(temp_dir) solo funciona si el dir está vacío, mejor usar rmtree
             # El borrado del archivo temporal dicom_path DEBE ocurrir dentro de segmentar_dicom 
             # o antes de rmtree si fue guardado en temp_dir.
             # Si segmentar_dicom no borra el archivo, shutil.rmtree es la forma segura
             import shutil
             shutil.rmtree(temp_dir)
             


@router.get("/series-mapping/")
def obtener_mapping_de_serie(
    session_id: str = Query(..., description="UUID de la serie cargada")
):
    """Obtiene el archivo mapping.json de la ruta persistente."""
    try:
        # 🔴 CORRECCIÓN: PERSISTENT_STORAGE_BASE ya contiene 'series'. 
        # Si el Mount Path es /api/static/series, la ruta es solo base + session_id
        mapping_path_str = os.path.join(PERSISTENT_STORAGE_BASE, session_id, "mapping.json")
        mapping_path = Path(mapping_path_str) 
        
        print(f"🛠 Buscando mapping en: {mapping_path}")

        if not mapping_path.exists():
            return JSONResponse(
                content={
                    "error": f"No se encontró el archivo de mapeo en {mapping_path_str}"
                },
                status_code=404,
            )

        with open(mapping_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {"mapping": data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/segmentar-desde-mapping/")
async def segmentar_desde_mapping(
    session_id: str = Form(...),
    image_name: str = Form(...),
    x_user_id: int = Header(..., alias="X-User-Id"),  
):
    """Segmenta un DICOM usando información y archivos cargados previamente desde la ruta persistente."""
    try:
        # 🔴 CORRECCIÓN: PERSISTENT_STORAGE_BASE ya contiene 'series'.
        base_dir = os.path.join(PERSISTENT_STORAGE_BASE, session_id)
        
        mapping_path = os.path.join(base_dir, "mapping.json")
        if not os.path.exists(mapping_path):
            raise FileNotFoundError("No se encontró el archivo mapping.json")

        with open(mapping_path, "r") as f:
            mapping = json.load(f)

        if image_name not in mapping:
            raise ValueError(f"No se encontró {image_name} en el mapping")

        dicom_info = mapping[image_name]
        # Aquí asumo que la clave es 'dicom_name' basada en el código de dicom_service.py
        dicom_filename = dicom_info["dicom_name"] 
        archivodicomid = dicom_info["archivodicomid"]

        # El dicom_path ahora apunta al archivo en el volumen persistente
        dicom_path = os.path.join(base_dir, dicom_filename)
        if not os.path.exists(dicom_path):
            raise FileNotFoundError(
                f"No se encontró el archivo DICOM: {dicom_filename} en {dicom_path}"
            )

        from ..services.segmentation_services import segmentar_dicom

        resultado = segmentar_dicom(
            dicom_path, archivodicomid=archivodicomid, user_id=x_user_id
        )

        return resultado
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------
@router.post("/segmentar-serie-3d/")
def segmentar_serie_3d_endpoint(
    session_id: str = Form(...),
    x_user_id: int = Header(..., alias="X-User-Id"),
    preset: str | None = Form(None),
    thr_min: float | None = Form(None),
    thr_max: float | None = Form(None),
    min_size_voxels: int = Form(2000),
    close_radius_mm: float = Form(1.5)
):
    try:
        return segmentar_serie_3d(
            session_id=session_id,
            user_id=x_user_id,
            preset=preset,
            thr_min=thr_min,
            thr_max=thr_max,
            min_size_voxels=min_size_voxels,
            close_radius_mm=close_radius_mm,
        )

    except Exception as e:
        raise HTTPException(500, str(e))

@router.delete("/historial/segmentaciones-3d/{seg3d_id}")
def borrar_segmentacion_3d_router(seg3d_id: int, x_user_id: int = Header(..., alias="X-User-Id")):
    try:
        ok = borrar_segmentacion_3d(seg3d_id, user_id=x_user_id)
        if not ok:
            raise HTTPException(status_code=404, detail="No encontrada")
        return {"mensaje": "Segmentación 3D eliminada"}
    except HTTPException: raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
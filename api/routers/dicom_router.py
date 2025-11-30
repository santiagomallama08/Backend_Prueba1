# api/routers/dicom_router.py
import tempfile
from typing import Optional
import uuid
import zipfile
from fastapi import APIRouter, Form, HTTPException, Path, UploadFile, File, Header
from fastapi.responses import JSONResponse
import os
import numpy as np
import pydicom
from fastapi import Query
import json
from pathlib import Path

# Importamos las rutas persistentes del volumen
from main import SERIES_DIR

from ..services.segmentation3d_service import segmentar_serie_3d
from ..services.dicom_service import convert_dicom_zip_to_png_paths

router = APIRouter()


# =============================================================
# 1) SUBIR DICOM SUELTO
# =============================================================
@router.post("/upload-dicom")
async def upload_dicom(file: UploadFile = File(...)):
    try:
        contents = await file.read()

        # Guardar archivo temporal SOLO para leer metadatos
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, file.filename)

        with open(temp_path, "wb") as f:
            f.write(contents)

        dicom = pydicom.dcmread(temp_path)

        metadata = {
            "PatientID": dicom.get("PatientID", "N/A"),
            "StudyDate": dicom.get("StudyDate", "N/A"),
            "Modality": dicom.get("Modality", "N/A"),
            "Rows": dicom.get("Rows", "N/A"),
            "Columns": dicom.get("Columns", "N/A"),
            "NumberOfFrames": dicom.get("NumberOfFrames", "1"),
            "SOPInstanceUID": dicom.get("SOPInstanceUID", "N/A"),
        }

        return JSONResponse(
            content={
                "message": "Archivo DICOM subido y procesado exitosamente.",
                "metadata": metadata,
            }
        )

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)



# =============================================================
# 2) SUBIR ZIP DE SERIE DICOM
# =============================================================
@router.post("/upload-dicom-series/")
async def upload_dicom_series(
    file: UploadFile = File(...),
    x_user_id: int = Header(..., alias="X-User-Id"),
):
    if not file.filename.endswith(".zip"):
        raise HTTPException(
            status_code=400,
            detail="Debe subir un archivo .zip con archivos DICOM",
        )
    try:
        zip_bytes = await file.read()

        # convert_dicom_zip_to_png_paths ya debe usar SERIES_DIR internamente
        image_paths = convert_dicom_zip_to_png_paths(zip_bytes, user_id=x_user_id)

        return JSONResponse(
            content={
                "message": f"{len(image_paths)} imágenes convertidas correctamente.",
                "image_series": image_paths,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# =============================================================
# 3) OBTENER MAPPING
# =============================================================
@router.get("/series-mapping/")
def obtener_mapping_de_serie(
    session_id: str = Query(..., description="UUID de la serie cargada"),
):
    try:
        mapping_path = SERIES_DIR / session_id / "mapping.json"

        if not mapping_path.exists():
            return JSONResponse(
                content={"error": f"No se encontró el mapeo en {mapping_path}"},
                status_code=404,
            )

        with open(mapping_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return {"mapping": data}

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)



# =============================================================
# 4) SEGMENTAR UNA IMAGEN SEGÚN MAPPING
# =============================================================
@router.post("/segmentar-desde-mapping/")
async def segmentar_desde_mapping(
    session_id: str = Form(...),
    image_name: str = Form(...),
    x_user_id: int = Header(..., alias="X-User-Id"),
):
    try:
        series_path = SERIES_DIR / session_id
        mapping_path = series_path / "mapping.json"

        if not mapping_path.exists():
            raise FileNotFoundError("mapping.json no encontrado")

        with open(mapping_path, "r") as f:
            mapping = json.load(f)

        if image_name not in mapping:
            raise ValueError(f"No se encontró {image_name} en el mapping")

        dicom_name = mapping[image_name]["dicom_name"]
        archivodicomid = mapping[image_name]["archivodicomid"]

        dicom_path = series_path / dicom_name

        if not dicom_path.exists():
            raise FileNotFoundError(
                f"No se encontró el archivo DICOM: {dicom_name}"
            )

        from ..services.segmentation_services import segmentar_dicom

        resultado = segmentar_dicom(
            str(dicom_path), archivodicomid=archivodicomid, user_id=x_user_id
        )

        return resultado

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)



# =============================================================
# 5) SEGMENTACIÓN 3D COMPLETA
# =============================================================
@router.post("/segmentar-serie-3d/")
def segmentar_serie_3d_endpoint(
    session_id: str = Form(...),
    x_user_id: int = Header(..., alias="X-User-Id"),
    preset: Optional[str] = Form(None),
    thr_min: Optional[float] = Form(None),
    thr_max: Optional[float] = Form(None),
    min_size_voxels: Optional[int] = Form(2000),
    close_radius_mm: Optional[float] = Form(1.5),
):
    try:
        result = segmentar_serie_3d(
            session_id,
            user_id=x_user_id,
            preset=preset,
            thr_min=thr_min,
            thr_max=thr_max,
            min_size_voxels=min_size_voxels,
            close_radius_mm=close_radius_mm,
        )
        return result

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

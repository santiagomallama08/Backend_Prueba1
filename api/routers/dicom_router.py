# api/routers/dicom_router.py
import tempfile
import json
import os
from pathlib import Path
from typing import Optional
import pydicom
import numpy as np
import zipfile

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Form,
    Header,
    HTTPException,
    Query
)
from fastapi.responses import JSONResponse

from config.paths import SERIES_DIR
from api.services.dicom_service import convert_dicom_zip_to_png_paths
from api.services.segmentation3d_service import segmentar_serie_3d

router = APIRouter()

# ========== 1. Subir DICOM suelto ==========
@router.post("/upload-dicom")
async def upload_dicom(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, file.filename)

        with open(temp_path, "wb") as f:
            f.write(contents)

        dcm = pydicom.dcmread(temp_path)

        metadata = {
            "PatientID": dcm.get("PatientID", "N/A"),
            "StudyDate": dcm.get("StudyDate", "N/A"),
            "Modality": dcm.get("Modality", "N/A"),
            "Rows": dcm.get("Rows", "N/A"),
            "Columns": dcm.get("Columns", "N/A"),
        }

        return {"message": "OK", "metadata": metadata}

    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)


# ========== 2. Subir ZIP serie DICOM ==========
@router.post("/upload-dicom-series/")
async def upload_dicom_series(
    file: UploadFile = File(...),
    x_user_id: int = Header(..., alias="X-User-Id"),
):
    if not file.filename.endswith(".zip"):
        raise HTTPException(400, "Debe subir un ZIP")

    try:
        zip_bytes = await file.read()
        result = convert_dicom_zip_to_png_paths(zip_bytes, user_id=x_user_id)
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


# ========== 3. Obtener mapping ==========
@router.get("/series-mapping/")
def get_mapping(session_id: str = Query(...)):
    mapping_path = SERIES_DIR / session_id / "mapping.json"

    if not mapping_path.exists():
        return JSONResponse({"error": "mapping.json no encontrado"}, 404)

    with open(mapping_path, "r") as f:
        return {"mapping": json.load(f)}


# ========== 4. Segmentación desde mapping ==========
@router.post("/segmentar-desde-mapping/")
async def segmentar_2d(
    session_id: str = Form(...),
    image_name: str = Form(...),
    x_user_id: int = Header(..., alias="X-User-Id"),
):
    try:
        series_path = SERIES_DIR / session_id
        mapping_path = series_path / "mapping.json"

        with open(mapping_path, "r") as f:
            mapping = json.load(f)

        if image_name not in mapping:
            raise ValueError("imagen no encontrada en mapping")

        dicom_name = mapping[image_name]["dicom_name"]
        archivodicomid = mapping[image_name]["archivodicomid"]
        dicom_path = series_path / dicom_name

        from api.services.segmentation_services import segmentar_dicom
        result = segmentar_dicom(str(dicom_path), archivodicomid, x_user_id)
        return result

    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)


# ========== 5. Segmentación 3D ==========
@router.post("/segmentar-serie-3d/")
def seg3d(
    session_id: str = Form(...),
    x_user_id: int = Header(..., alias="X-User-Id"),
    preset: Optional[str] = Form(None),
    thr_min: Optional[float] = Form(None),
    thr_max: Optional[float] = Form(None),
):
    try:
        return segmentar_serie_3d(
            session_id=session_id,
            user_id=x_user_id,
            preset=preset,
            thr_min=thr_min,
            thr_max=thr_max,
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)

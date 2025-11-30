# api/routers/dicom_router.py
import tempfile
from typing import Optional
import json
import uuid
import zipfile
import os
import numpy as np
import pydicom
from pathlib import Path
from fastapi import (
    APIRouter,
    Form,
    HTTPException,
    UploadFile,
    File,
    Header,
    Query
)
from fastapi.responses import JSONResponse

# Importar servicios
from ..services.segmentation3d_service import segmentar_serie_3d
from ..services.dicom_service import convert_dicom_zip_to_png_paths

router = APIRouter()

# =============================================================
# 🔥 DEFINICIÓN CORRECTA DE SERIES_DIR SIN IMPORTAR main.py
# =============================================================

BASE_DIR = Path(__file__).resolve().parents[2]  # /app
STATIC_DIR = BASE_DIR / "api" / "static"
SERIES_DIR = STATIC_DIR / "series"
SEG3D_DIR = STATIC_DIR / "segmentations3d"

os.makedirs(SERIES_DIR, exist_ok=True)
os.makedirs(SEG3D_DIR, exist_ok=True)


# =============================================================
# 1) SUBIR DICOM SUELTO
# =============================================================
@router.post("/upload-dicom")
async def upload_dicom(file: UploadFile = File(...)):
    try:
        contents = await file.read()

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

        return {
            "message": "Archivo DICOM subido y procesado correctamente",
            "metadata": metadata,
        }

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# =============================================================
# 2) SUBIR ZIP DE SERIE DICOM
# =============================================================
@router.post("/upload-dicom-series/")
async def upload_dicom_series(
    file: UploadFile = File(...),
    x_user_id: int = Header(..., alias="X-User-Id"),
):
    if not file.filename.endswith(".zip"):
        raise HTTPException(400, "Debe subir un archivo .zip con DICOMs")

    try:
        zip_bytes = await file.read()

        image_paths = convert_dicom_zip_to_png_paths(zip_bytes, user_id=x_user_id)

        return {
            "message": f"{len(image_paths)} imágenes convertidas correctamente.",
            "image_series": image_paths,
        }

    except Exception as e:
        raise HTTPException(500, str(e))


# =============================================================
# 3) OBTENER MAPPING DE UNA SERIE
# =============================================================
@router.get("/series-mapping/")
def obtener_mapping_de_serie(
    session_id: str = Query(..., description="UUID de la serie cargada"),
):
    try:
        mapping_path = SERIES_DIR / session_id / "mapping.json"

        if not mapping_path.exists():
            return JSONResponse(
                {"error": f"No se encontró el mapeo: {mapping_path}"}, status_code=404
            )

        with open(mapping_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return {"mapping": data}

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# =============================================================
# 4) SEGMENTAR DESDE MAPPING (2D)
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
            raise ValueError(f"{image_name} no está en mapping")

        dicom_name = mapping[image_name]["dicom_name"]
        archivodicomid = mapping[image_name]["archivodicomid"]

        dicom_path = series_path / dicom_name

        if not dicom_path.exists():
            raise FileNotFoundError(f"DICOM no encontrado: {dicom_name}")

        from ..services.segmentation_services import segmentar_dicom

        resultado = segmentar_dicom(
            str(dicom_path),
            archivodicomid=archivodicomid,
            user_id=x_user_id
        )

        return resultado

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


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
            session_id=session_id,
            user_id=x_user_id,
            preset=preset,
            thr_min=thr_min,
            thr_max=thr_max,
            min_size_voxels=min_size_voxels,
            close_radius_mm=close_radius_mm,
        )

        return result

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

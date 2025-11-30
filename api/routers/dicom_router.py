import tempfile
from PIL import Image
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

from ..services.segmentation3d_service import segmentar_serie_3d
from ..services.dicom_service import convert_dicom_zip_to_png_paths

router = APIRouter()

# 🔥 Ruta fija donde Railway montó tu volumen
VOLUME_BASE = Path("/app/api/static/series")


@router.post("/upload-dicom")
async def upload_dicom(file: UploadFile = File(...)):
    try:
        with tempfile.NamedTemporaryFile(delete=True, suffix=file.filename) as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name

            dicom = pydicom.dcmread(tmp_path)

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


@router.post("/upload-dicom-series/")
async def upload_dicom_series(
    file: UploadFile = File(...),
    x_user_id: int = Header(..., alias="X-User-Id"),
):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Debe subir un archivo .zip con archivos DICOM")

    try:
        zip_bytes = await file.read()

        result = convert_dicom_zip_to_png_paths(
            zip_bytes,
            user_id=x_user_id,
            base_output_dir="/app/api/static/series"   # VOLUMEN REAL
        )

        return JSONResponse(content=result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/segmentar-dicom/")
async def segmentar_dicom_endpoint(file: UploadFile = File(...)):
    try:
        with tempfile.NamedTemporaryFile(delete=True, suffix=file.filename) as tmp:
            contents = await file.read()
            tmp.write(contents)
            dicom_path = tmp.name

            from ..services.segmentation_services import segmentar_dicom
            resultado = segmentar_dicom(dicom_path)

            return resultado

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@router.get("/series-mapping/")
def obtener_mapping_de_serie(session_id: str = Query(..., description="UUID de la serie cargada")):
    try:
        # 🔥 mapping REAL en el volumen
        mapping_path = VOLUME_BASE / session_id / "mapping.json"

        if not mapping_path.exists():
            return JSONResponse(
                content={"error": f"No se encontró el archivo de mapeo en {mapping_path}"},
                status_code=404,
            )

        with open(mapping_path, "r", encoding="utf-8") as f:
            return {"mapping": json.load(f)}

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@router.post("/segmentar-desde-mapping/")
async def segmentar_desde_mapping(
    session_id: str = Form(...),
    image_name: str = Form(...),
    x_user_id: int = Header(..., alias="X-User-Id"),
):
    try:
        base_dir = VOLUME_BASE / session_id
        mapping_path = base_dir / "mapping.json"

        if not mapping_path.exists():
            raise FileNotFoundError("No se encontró el archivo mapping.json")

        with open(mapping_path, "r") as f:
            mapping = json.load(f)

        if image_name not in mapping:
            raise ValueError(f"No se encontró {image_name} en el mapping")

        dicom_info = mapping[image_name]
        dicom_filename = dicom_info["dicom_name"]
        archivodicomid = dicom_info["archivodicomid"]

        dicom_path = base_dir / dicom_filename
        if not dicom_path.exists():
            raise FileNotFoundError(f"No se encontró el archivo DICOM: {dicom_filename}")

        from ..services.segmentation_services import segmentar_dicom

        return segmentar_dicom(
            str(dicom_path),
            archivodicomid=archivodicomid,
            user_id=x_user_id,
        )

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


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
        return segmentar_serie_3d(
            session_id,
            user_id=x_user_id,
            preset=preset,
            thr_min=thr_min,
            thr_max=thr_max,
            min_size_voxels=min_size_voxels,
            close_radius_mm=close_radius_mm,
        )
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

# api/routers/dicom_router.py

import tempfile
from fastapi import APIRouter, Form, HTTPException, UploadFile, File, Header, Query
from fastapi.responses import JSONResponse
from pathlib import Path
import pydicom
import json

from ..services.dicom_service import convert_dicom_zip_to_png_paths
from ..services.segmentation_services import segmentar_dicom
from ..services.segmentation3d_service import segmentar_serie_3d

router = APIRouter()

# 🔥 Volumen real montado en Railway
VOLUME_BASE = Path("/app/api/static/series")


# -------------------------------------------------------
# 1) SUBIR UN SOLO DICOM
# -------------------------------------------------------
@router.post("/upload-dicom")
async def upload_dicom(file: UploadFile = File(...)):
    try:
        with tempfile.NamedTemporaryFile(delete=True, suffix=file.filename) as tmp:
            contents = await file.read()
            tmp.write(contents)

            dicom = pydicom.dcmread(tmp.name)

            metadata = {
                "PatientID": dicom.get("PatientID", "N/A"),
                "StudyDate": dicom.get("StudyDate", "N/A"),
                "Modality": dicom.get("Modality", "N/A"),
                "Rows": dicom.get("Rows", "N/A"),
                "Columns": dicom.get("Columns", "N/A"),
            }

            return {"message": "DICOM leído correctamente", "metadata": metadata}

    except Exception as e:
        raise HTTPException(500, f"Error leyendo DICOM: {e}")


# -------------------------------------------------------
# 2) SUBIR ZIP CON LA SERIE COMPLETA
# -------------------------------------------------------
@router.post("/upload-dicom-series/")
async def upload_dicom_series(
    file: UploadFile = File(...),
    x_user_id: int = Header(..., alias="X-User-Id")
):
    if not file.filename.endswith(".zip"):
        raise HTTPException(400, "Debe subir un archivo .zip con DICOMs")

    try:
        zip_bytes = await file.read()

        # ❗ NO PASAMOS base_dir porque tu función no lo acepta
        result = convert_dicom_zip_to_png_paths(zip_bytes, x_user_id)

        return JSONResponse(result)

    except Exception as e:
        raise HTTPException(500, str(e))


# -------------------------------------------------------
# 3) OBTENER MAPPING.JSON DESDE EL VOLUMEN
# -------------------------------------------------------
@router.get("/series-mapping/")
def obtener_mapping_de_serie(
    session_id: str = Query(..., description="ID de la serie")
):
    try:
        mapping_path = VOLUME_BASE / session_id / "mapping.json"

        if not mapping_path.exists():
            raise HTTPException(404, f"mapping.json no existe: {mapping_path}")

        with open(mapping_path, "r", encoding="utf-8") as f:
            return {"mapping": json.load(f)}

    except Exception as e:
        raise HTTPException(500, str(e))


# -------------------------------------------------------
# 4) SEGMENTAR UNA IMAGEN INDIVIDUAL
# -------------------------------------------------------
@router.post("/segmentar-desde-mapping/")
async def segmentar_desde_mapping(
    session_id: str = Form(...),
    image_name: str = Form(...),
    x_user_id: int = Header(..., alias="X-User-Id")
):
    try:
        serie_dir = VOLUME_BASE / session_id
        mapping_path = serie_dir / "mapping.json"

        if not mapping_path.exists():
            raise HTTPException(404, "mapping.json no encontrado")

        with open(mapping_path, "r") as f:
            mapping = json.load(f)

        if image_name not in mapping:
            raise HTTPException(400, "La imagen no existe en el mapping")

        dicom_filename = mapping[image_name]["dicom_name"]
        archivodicomid = mapping[image_name]["archivodicomid"]

        dicom_path = serie_dir / dicom_filename

        if not dicom_path.exists():
            raise HTTPException(404, f"DICOM no encontrado: {dicom_filename}")

        return segmentar_dicom(str(dicom_path), archivodicomid=archivodicomid, user_id=x_user_id)

    except Exception as e:
        raise HTTPException(500, str(e))


# -------------------------------------------------------
# 5) SEGMENTACIÓN 3D
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

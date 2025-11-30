# api/routers/dicom_router.py
import tempfile
from fastapi import APIRouter, Form, HTTPException, Path, UploadFile, File, Header, Query
from fastapi.responses import JSONResponse
from pathlib import Path
import pydicom
import json

from ..services.segmentation3d_service import segmentar_serie_3d
from ..services.dicom_service import convert_dicom_zip_to_png_paths

router = APIRouter()

# 📌 Ruta GLOBAL del volumen montado en Railway (NO CAMBIAR)
VOLUME_BASE = Path("/app/api/static/series")


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
                "NumberOfFrames": dicom.get("NumberOfFrames", "1"),
                "SOPInstanceUID": dicom.get("SOPInstanceUID", "N/A"),
            }

            return {
                "message": "Archivo DICOM procesado correctamente",
                "metadata": metadata,
            }

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@router.post("/upload-dicom-series/")
async def upload_dicom_series(
    file: UploadFile = File(...),
    x_user_id: int = Header(..., alias="X-User-Id"),
):
    """Carga ZIP DICOM y lo guarda en el volumen."""
    if not file.filename.endswith(".zip"):
        raise HTTPException(
            status_code=400, detail="Debe subir un archivo .zip con archivos DICOM"
        )

    try:
        zip_bytes = await file.read()

        # 🔥 GUARDA AUTOMÁTICAMENTE EN EL VOLUMEN (convert_dicom... ya usa api/static/series)
        result = convert_dicom_zip_to_png_paths(zip_bytes, user_id=x_user_id)

        return JSONResponse(content=result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/series-mapping/")
def obtener_mapping_de_serie(
    session_id: str = Query(..., description="UUID de la serie cargada")
):
    """Obtiene el mapping.json desde el volumen."""
    try:
        mapping_path = VOLUME_BASE / session_id / "mapping.json"

        if not mapping_path.exists():
            return JSONResponse(
                content={"error": f"No existe mapping.json en {mapping_path}"},
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
    """Segmenta una imagen usando mapping.json desde el volumen."""
    try:
        base_dir = VOLUME_BASE / session_id
        mapping_path = base_dir / "mapping.json"

        if not mapping_path.exists():
            raise FileNotFoundError("No existe mapping.json")

        with open(mapping_path, "r") as f:
            mapping = json.load(f)

        if image_name not in mapping:
            raise ValueError(f"No se encuentra {image_name} en mapping.json")

        dicom_filename = mapping[image_name]["dicom_name"]
        archivodicomid = mapping[image_name]["archivodicomid"]

        dicom_path = base_dir / dicom_filename
        if not dicom_path.exists():
            raise FileNotFoundError(f"No existe el archivo DICOM: {dicom_filename}")

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
    preset: str | None = Form(None),
    thr_min: float | None = Form(None),
    thr_max: float | None = Form(None),
    min_size_voxels: int = Form(2000),
    close_radius_mm: float = Form(1.5),
):
    """Segmentación completa 3D usando los archivos guardados en el volumen."""
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
        return JSONResponse(content={"error": str(e)}, status_code=500)

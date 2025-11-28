from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import FileResponse
from api.services.reportes_service import generar_reporte_estudio
from pathlib import Path

router = APIRouter(prefix="/reportes", tags=["Reportes"])

@router.post("/generar/{session_id}")
def generar_reporte_endpoint(
    session_id: str,
    x_user_id: int = Header(..., alias="X-User-Id")
):
    """Genera un reporte PDF completo del estudio"""
    try:
        pdf_path = generar_reporte_estudio(session_id, x_user_id)
        return {"message": "Reporte generado exitosamente", "pdf_url": pdf_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/descargar/{filename}")
def descargar_reporte(filename: str):
    """Descarga un reporte PDF generado"""
    file_path = Path(f"api/static/reportes/{filename}")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    
    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=filename
    )

# api/routers/modelos3d_router.py
from fastapi import APIRouter, HTTPException, Path, Header, Query, Form
from typing import Optional

from api.services.modelos3d_services import (
    exportar_stl_desde_seg3d,
    listar_modelos3d,
    borrar_modelo3d,
)

router = APIRouter(prefix="/series", tags=["Modelos3D"])

@router.post("/{session_id}/export-stl")
def export_stl(
    session_id: str = Path(...),
    x_user_id: int = Header(None, alias="X-User-Id"),
    seg3d_id_q: Optional[int] = Query(None, description="ID de segmentación 3D (query)"),
    seg3d_id_f: Optional[int] = Form(None, description="ID de segmentación 3D (form)")
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Falta X-User-Id")

    seg3d_id = seg3d_id_f if seg3d_id_f is not None else seg3d_id_q  

    try:
        return exportar_stl_desde_seg3d(session_id, int(x_user_id), seg3d_id)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except FileNotFoundError as fe:
        raise HTTPException(status_code=404, detail=str(fe))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{session_id}/modelos3d")
def listar_modelos(
    session_id: str = Path(...),
    x_user_id: int = Header(None, alias="X-User-Id")
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Falta X-User-Id")
    try:
        return listar_modelos3d(session_id, int(x_user_id))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/modelos3d/{modelo_id}")
def eliminar_modelo(
    modelo_id: int = Path(...),
    x_user_id: int = Header(None, alias="X-User-Id")
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Falta X-User-Id")
    try:
        ok = borrar_modelo3d(int(modelo_id), int(x_user_id))
        if not ok:
            raise HTTPException(status_code=404, detail="Modelo no encontrado")
        return {"message": "Modelo borrado"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

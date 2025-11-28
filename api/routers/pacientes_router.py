from fastapi import APIRouter, HTTPException, Header
from typing import List
from api.models.schemas import (
    PacienteCreate, 
    PacienteUpdate, 
    PacienteOut,
    EstudioPacienteCreate,
    EstudioPacienteOut
)
from api.services.pacientes_services import (
    crear_paciente,
    listar_pacientes,
    obtener_paciente,
    actualizar_paciente,
    eliminar_paciente,
    vincular_estudio,
    listar_estudios_paciente,
    eliminar_estudio
)

router = APIRouter(prefix="/pacientes", tags=["Pacientes"])

# ============ PACIENTES ============

@router.post("/", response_model=dict)
def crear_paciente_endpoint(
    paciente: PacienteCreate,
    x_user_id: int = Header(..., alias="X-User-Id")
):
    try:
        paciente_id = crear_paciente(paciente.dict(), x_user_id)
        return {"id": paciente_id, "message": "Paciente creado exitosamente"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[PacienteOut])
def listar_pacientes_endpoint(
    x_user_id: int = Header(..., alias="X-User-Id")
):
    try:
        return listar_pacientes(x_user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{paciente_id}", response_model=PacienteOut)
def obtener_paciente_endpoint(
    paciente_id: int,
    x_user_id: int = Header(..., alias="X-User-Id")
):
    paciente = obtener_paciente(paciente_id, x_user_id)
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    return paciente


@router.put("/{paciente_id}")
def actualizar_paciente_endpoint(
    paciente_id: int,
    paciente: PacienteUpdate,
    x_user_id: int = Header(..., alias="X-User-Id")
):
    try:
        ok = actualizar_paciente(paciente_id, paciente.dict(exclude_unset=True), x_user_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Paciente no encontrado")
        return {"message": "Paciente actualizado exitosamente"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{paciente_id}")
def eliminar_paciente_endpoint(
    paciente_id: int,
    x_user_id: int = Header(..., alias="X-User-Id")
):
    try:
        ok = eliminar_paciente(paciente_id, x_user_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Paciente no encontrado")
        return {"message": "Paciente eliminado exitosamente"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ ESTUDIOS ============

@router.post("/{paciente_id}/estudios")
def vincular_estudio_endpoint(
    paciente_id: int,
    estudio: EstudioPacienteCreate,
    x_user_id: int = Header(..., alias="X-User-Id")
):
    try:
        estudio_id = vincular_estudio(paciente_id, estudio.dict(), x_user_id)
        return {"id": estudio_id, "message": "Estudio vinculado exitosamente"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{paciente_id}/estudios", response_model=List[EstudioPacienteOut])
def listar_estudios_endpoint(
    paciente_id: int,
    x_user_id: int = Header(..., alias="X-User-Id")
):
    try:
        return listar_estudios_paciente(paciente_id, x_user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/estudios/{estudio_id}")
def eliminar_estudio_endpoint(
    estudio_id: int,
    x_user_id: int = Header(..., alias="X-User-Id")
):
    try:
        ok = eliminar_estudio(estudio_id, x_user_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Estudio no encontrado")
        return {"message": "Estudio desvinculado exitosamente"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

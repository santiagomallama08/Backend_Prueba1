# api/models/schemas.py
from datetime import date, datetime
from pydantic import BaseModel, EmailStr
from typing import Optional


class RegisterInput(BaseModel):
    nombre_completo: str
    email: EmailStr
    password: str
    rol: str = "usuario"


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class ArchivoDicomOut(BaseModel):
    archivodicomid: int
    nombrearchivo: str
    rutaarchivo: str
    fechacarga: date
    sistemaid: int
    session_id: str | None = None
    has_segmentations: bool = False
    seg_count: int = 0


# ============ PACIENTES ============


class PacienteBase(BaseModel):
    nombre_completo: str
    documento: str
    tipo_documento: Optional[str] = "CC"
    fecha_nacimiento: Optional[date] = None
    edad: Optional[int] = None
    sexo: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    notas: Optional[str] = None


class PacienteCreate(PacienteBase):
    pass


class PacienteUpdate(BaseModel):
    nombre_completo: Optional[str] = None
    documento: Optional[str] = None
    tipo_documento: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    edad: Optional[int] = None
    sexo: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    notas: Optional[str] = None


class PacienteOut(PacienteBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ ESTUDIOS PACIENTE ============


class EstudioPacienteCreate(BaseModel):
    session_id: str
    fecha_estudio: Optional[date] = None
    tipo_estudio: Optional[str] = None
    diagnostico: Optional[str] = None
    notas: Optional[str] = None


class EstudioPacienteOut(BaseModel):
    id: int
    paciente_id: int
    session_id: str
    fecha_estudio: Optional[date]
    tipo_estudio: Optional[str]
    diagnostico: Optional[str]
    notas: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

# models/protesis_dimension_model.py
from pydantic import BaseModel
from typing import Optional

class ProtesisDimensionCreate(BaseModel):
    archivodicomid: int
    altura: float
    volumen: float
    longitud: float
    ancho: float
    tipoprotesis: str
    unidad: str = "mm³"
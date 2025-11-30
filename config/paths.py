# config/paths.py
from pathlib import Path
import os

# Ruta base del volumen persistente de Railway
BASE_STATIC_DIR = Path("/data/static")

# Crear si no existe
BASE_STATIC_DIR.mkdir(parents=True, exist_ok=True)

# Subrutas persistentes
SERIES_DIR = BASE_STATIC_DIR / "series"
REPORTES_DIR = BASE_STATIC_DIR / "reportes"
MODELOS3D_DIR = BASE_STATIC_DIR / "modelos3d"
SEGMENTATIONS_3D_DIR = BASE_STATIC_DIR / "segmentations3d"

SERIES_DIR.mkdir(parents=True, exist_ok=True)
REPORTES_DIR.mkdir(parents=True, exist_ok=True)
MODELOS3D_DIR.mkdir(parents=True, exist_ok=True)
SEGMENTATIONS_3D_DIR.mkdir(parents=True, exist_ok=True)

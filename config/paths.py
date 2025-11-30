# config/paths.py
from pathlib import Path

# ============================================================
#      BASE PERSISTENTE DEL VOLUMEN MONTADO EN RAILWAY
# ============================================================

# Esta es SIEMPRE la raíz del volumen en Railway:
BASE_STATIC_DIR = Path("/data/static")

# Crear carpeta si no existe (Railway siempre deja escribir aquí)
BASE_STATIC_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
#      RUTAS INTERNAS (subcarpetas dentro del volumen)
# ============================================================

# /data/static/series
SERIES_DIR = BASE_STATIC_DIR / "series"
SERIES_DIR.mkdir(parents=True, exist_ok=True)

# /data/static/segmentations2d
SEGMENTATIONS_2D_DIR = BASE_STATIC_DIR / "segmentations2d"
SEGMENTATIONS_2D_DIR.mkdir(parents=True, exist_ok=True)

# /data/static/segmentations3d
SEGMENTATIONS_3D_DIR = BASE_STATIC_DIR / "segmentations3d"
SEGMENTATIONS_3D_DIR.mkdir(parents=True, exist_ok=True)

# /data/static/modelos3d
MODELOS3D_DIR = BASE_STATIC_DIR / "modelos3d"
MODELOS3D_DIR.mkdir(parents=True, exist_ok=True)

# /data/static/reportes
REPORTES_DIR = BASE_STATIC_DIR / "reportes"
REPORTES_DIR.mkdir(parents=True, exist_ok=True)

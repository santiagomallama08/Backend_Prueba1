# config/paths.py

from pathlib import Path
import os

"""
Archivo centralizado para la definición de rutas persistentes.
Este archivo **NO IMPORTA main.py**, para evitar ciclos.

Todas las rutas aquí son usadas por:
- dicom_service
- segmentation_services (2D)
- segmentation3d_service (3D)
- modelos3d_service
- reportes_service
- historial_service
"""

# ===============================================================
# 📌 1. Ruta base del volumen persistente en Railway
# ===============================================================
# En Railway, el volumen siempre se monta en:  /data
# Tú montaste /data/static → aquí guardamos series, segmentaciones, reportes…
# ===============================================================

BASE_STATIC_DIR = Path("/data/static")

# Crear la carpeta si no existe
BASE_STATIC_DIR.mkdir(parents=True, exist_ok=True)


# ===============================================================
# 📌 2. Subcarpetas persistentes
# ===============================================================

# SERIES DICOM
SERIES_DIR = BASE_STATIC_DIR / "series"
SERIES_DIR.mkdir(parents=True, exist_ok=True)

# SEGMENTACIONES 2D
SEGMENTATIONS_2D_DIR = BASE_STATIC_DIR / "segmentations"
SEGMENTATIONS_2D_DIR.mkdir(parents=True, exist_ok=True)

# SEGMENTACIONES 3D (mask.npy + thumbs + stl temp)
SEGMENTATIONS_3D_DIR = BASE_STATIC_DIR / "segmentations3d"
SEGMENTATIONS_3D_DIR.mkdir(parents=True, exist_ok=True)

# REPORTES PDF
REPORTES_DIR = BASE_STATIC_DIR / "reportes"
REPORTES_DIR.mkdir(parents=True, exist_ok=True)

# MODELOS 3D (STL finales)
MODELOS3D_DIR = BASE_STATIC_DIR / "modelos3d"
MODELOS3D_DIR.mkdir(parents=True, exist_ok=True)


# ===============================================================
# 📌 3. Debug opcional para verificar en Railway
# ===============================================================
print("🔥 [paths.py] Directorios configurados:")
print(f"BASE_STATIC_DIR      → {BASE_STATIC_DIR}")
print(f"SERIES_DIR           → {SERIES_DIR}")
print(f"SEGMENTATIONS_2D_DIR → {SEGMENTATIONS_2D_DIR}")
print(f"SEGMENTATIONS_3D_DIR → {SEGMENTATIONS_3D_DIR}")
print(f"REPORTES_DIR         → {REPORTES_DIR}")
print(f"MODELOS3D_DIR        → {MODELOS3D_DIR}")

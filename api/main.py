"""
DICOM API - Sistema de análisis de imágenes médicas
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import logging
import os # 👈 Importación requerida
from pathlib import Path


# Importar routers
from api.routers import (
    login_router,
    dicom_router,
    historial_router,
    modelos3d_router,
    pacientes_router,
    reportes_router,
    
)

# ============ Configuración de logging ============
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ❗ RUTA DE ALMACENAMIENTO PERSISTENTE (Volume)
# Obtiene la ruta del volumen de la variable de entorno de Railway.
# Si no está definida (ej. desarrollo local), usa la ruta local por defecto.
STORAGE_BASE_PATH = os.environ.get(
    "STORAGE_BASE_PATH", 
    Path("api/static/series").absolute() # Usar Path para la ruta local
)

# ============ Inicializar aplicación ============
app = FastAPI(
    title="DICOM Medical Imaging API",
    version="1.1.0",
    description="API para procesamiento de imágenes médicas DICOM",
)


# ============ Middleware de errores ============
@app.middleware("http")
async def error_handler(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        logger.error(f"Error en {request.method} {request.url.path}: {str(exc)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Error interno del servidor", "detail": str(exc)},
        )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ Archivos estáticos ============

# 1. Montar la ruta estática para la SERIE DE IMÁGENES usando el Volume
# URL Pública: /static/series/* ->  Ruta Física: [STORAGE_BASE_PATH]/*
Path(STORAGE_BASE_PATH).mkdir(parents=True, exist_ok=True) # Crear la carpeta si no existe en el volumen
app.mount(
    "/static/series", 
    StaticFiles(directory=STORAGE_BASE_PATH), 
    name="series_static"
)
logger.info(f"Ruta de Volúmenes (Storage Base Path): {STORAGE_BASE_PATH}")


# 2. Montar otros archivos estáticos (ej: CSS, JS) si existen en api/static/ (ruta efímera)
# Esto mantiene el comportamiento original de /static/
# Nota: Si todos tus archivos estáticos están en la carpeta de la serie, puedes eliminar este bloque.
app.mount("/static", StaticFiles(directory="api/static"), name="static")
logger.info(f"Ruta Estática Efímera (api/static): {Path('api/static').absolute()}")


# ============ Rutas principales ============
@app.get("/")
def root():
    return {
        "status": "online",
        "message": "API DICOM funcionando correctamente",
        "version": "1.1.0",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "modules": ["auth", "dicom", "historial", "modelos3d", "pacientes"],
    }


# ============ Incluir routers ============
app.include_router(login_router.router, tags=["Auth"])
app.include_router(dicom_router.router, tags=["DICOM"])
app.include_router(historial_router.router, tags=["Historial"])
app.include_router(modelos3d_router.router, tags=["Modelos3D"])
app.include_router(pacientes_router.router, tags=["Pacientes"])
app.include_router(reportes_router.router, tags=["Reportes"])


# ============ Eventos ============
@app.on_event("startup")
async def startup():
    logger.info("=" * 50)
    logger.info("Iniciando DICOM API v1.1.0")
    # logger.info(f"Static path: {static_path.absolute()}") # Se elimina, ya se loguea arriba
    logger.info("=" * 50)


@app.on_event("shutdown")
async def shutdown():
    logger.info("Cerrando DICOM API")
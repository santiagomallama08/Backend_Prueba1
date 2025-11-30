"""
DICOM API - Sistema de análisis de imágenes médicas
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import logging
from pathlib import Path
from config.paths import BASE_STATIC_DIR, SERIES_DIR, REPORTES_DIR, MODELOS3D_DIR

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
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============ Inicializar aplicación ============
app = FastAPI(
    title="DICOM Medical Imaging API",
    version="1.1.0",
    description="API para procesamiento de imágenes médicas DICOM",
)

# ============ Manejo global de errores ============
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

# ============ CORS ============
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Ajusta si usas dominios específicos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
#                ARCHIVOS ESTÁTICOS (PERSISTENTES)
# ============================================================

# Ruta del volumen persistente montado en Railway
BASE_STATIC_DIR = Path("/data/static")

# Crear el directorio si no existe (persistente)
BASE_STATIC_DIR.mkdir(parents=True, exist_ok=True)

# Montar /static -> /data/static
app.mount("/static", StaticFiles(directory=BASE_STATIC_DIR), name="static")






logger.info(f" Directorio persistente BASE_STATIC_DIR: {BASE_STATIC_DIR}")
logger.info(f" SERIES_DIR: {SERIES_DIR}")
logger.info(f" REPORTES_DIR: {REPORTES_DIR}")
logger.info(f" MODELOS3D_DIR: {MODELOS3D_DIR}")

# ============================================================

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
        "static_path": str(BASE_STATIC_DIR),
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
    logger.info("=" * 60)
    logger.info("Iniciando DICOM API v1.1.0")
    logger.info(f"Static path persistente: {BASE_STATIC_DIR.absolute()}")
    logger.info("=" * 60)

@app.on_event("shutdown")
async def shutdown():
    logger.info("Cerrando DICOM API")

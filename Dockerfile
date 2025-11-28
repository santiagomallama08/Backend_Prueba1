# Usa una imagen base de Python oficial y optimizada
FROM python:3.11-slim

# Establece el directorio de trabajo, que es /app. 
# Esta es la base para tu ruta de volumen: /app/static/series
WORKDIR /app

# Copia solo el archivo de dependencias primero
COPY requirements.txt .

# Instala las dependencias necesarias para tu aplicación (incluyendo pydicom, fastapi, etc.)
# y los paquetes de producción (Gunicorn, uvicorn workers)
RUN pip install --no-cache-dir -r requirements.txt gunicorn uvicorn[standard]

# Copia el resto del código de la aplicación
COPY . .

# Expón el puerto que usa tu aplicación
EXPOSE 8000

# Comando de Ejecución de Producción (Usando Gunicorn con Uvicorn workers)
# -w 4:  Define 4 workers (ajusta según los recursos de tu plan en Railway)
# api.main:app: Ejecuta la aplicación 'app' que se encuentra en api/main.py
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "api.main:app", "-b", "0.0.0.0:8000"]
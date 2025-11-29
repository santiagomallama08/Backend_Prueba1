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

CMD ["sh", "-c", "gunicorn -w 4 -k uvicorn.workers.UvicornWorker api.main:app -b 0.0.0.0:$PORT"]

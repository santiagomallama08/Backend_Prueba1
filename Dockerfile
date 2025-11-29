# Usa una imagen base ligera
FROM python:3.11-slim

# Establecemos el directorio de trabajo
WORKDIR /app

# Copiamos requirements
COPY requirements.txt .

# Instalamos dependencias
RUN pip install --no-cache-dir -r requirements.txt gunicorn uvicorn[standard]

# Copiamos toda la aplicación
COPY . .

# Railway asigna dinámicamente el puerto → EXPOSE es opcional
# EXPOSE 8000   # puedes quitarlo o dejarlo, no afecta

# Comando CORREGIDO:
# Usamos "sh -c" para que la variable $PORT se expanda correctamente
CMD ["sh", "-c", "gunicorn -w 4 -k uvicorn.workers.UvicornWorker api.main:app -b 0.0.0.0:$PORT"]

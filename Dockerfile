FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt gunicorn uvicorn[standard]

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "gunicorn -w 4 -k uvicorn.workers.UvicornWorker api.main:app -b 0.0.0.0:$PORT"]

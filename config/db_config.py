import os
import psycopg2
from urllib.parse import urlparse

def get_connection():
    DATABASE_URL = os.getenv("DATABASE_URL")

    if not DATABASE_URL:
        raise ValueError("DATABASE_URL no está configurada.")

    result = urlparse(DATABASE_URL)

    return psycopg2.connect(
        dbname=result.path[1:],      
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port
    )

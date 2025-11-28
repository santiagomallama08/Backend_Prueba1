# api/services/login_services.py

import psycopg2
from config.db_config import get_connection
from ..utils.hashing import hash_password, verify_password


def registrar_usuario(
    nombre_completo: str, email: str, password: str, rol: str = "usuario"
) -> tuple[bool, str]:
    """
    Registra un nuevo usuario en la tabla login_usuarios.
    Devuelve (True, mensaje) o (False, mensaje_error).
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        hashed_pw = hash_password(password)
        cur.execute(
            """
            INSERT INTO login_usuarios (nombre_completo, email, contraseña, rol)
            VALUES (%s, %s, %s, %s)
            """,
            (nombre_completo, email, hashed_pw, rol),
        )
        conn.commit()
        return True, "Registro exitoso"
    except psycopg2.Error as e:
        return False, f"Error en registro: {e.pgerror or str(e)}"
    finally:
        if conn:
            cur.close()
            conn.close()


def verificar_credenciales(email: str, password: str) -> bool:
    """
    Verifica si las credenciales (email + password) son correctas.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT contraseña FROM login_usuarios WHERE email = %s", (email,))
        row = cur.fetchone()
        if not row:
            return False
        hashed_pw = row[0]
        return verify_password(password, hashed_pw)
    finally:
        if conn:
            cur.close()
            conn.close()


def obtener_id_usuario(email: str):
    """
    Devuelve (id, nombre_completo) del usuario dado su email,
    o None si no existe.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, nombre_completo FROM login_usuarios WHERE email = %s", (email,)
        )
        row = cur.fetchone()
        return (row[0], row[1]) if row else None
    finally:
        if conn:
            cur.close()
            conn.close()

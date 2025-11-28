from datetime import date, datetime
from typing import List, Optional
from config.db_config import get_connection

# ============ PACIENTES ============


def crear_paciente(data: dict, user_id: int) -> int:
    """Crea un nuevo paciente y retorna su ID"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            INSERT INTO pacientes 
            (user_id, nombre_completo, documento, tipo_documento, fecha_nacimiento, 
             edad, sexo, telefono, email, direccion, ciudad, notas)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                user_id,
                data.get("nombre_completo"),
                data.get("documento"),
                data.get("tipo_documento", "CC"),
                data.get("fecha_nacimiento"),
                data.get("edad"),
                data.get("sexo"),
                data.get("telefono"),
                data.get("email"),
                data.get("direccion"),
                data.get("ciudad"),
                data.get("notas"),
            ),
        )
        paciente_id = cur.fetchone()[0]
        conn.commit()
        return paciente_id
    finally:
        cur.close()
        conn.close()


def listar_pacientes(user_id: int) -> List[dict]:
    """Lista todos los pacientes del usuario"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT id, user_id, nombre_completo, documento, tipo_documento, 
                   fecha_nacimiento, edad, sexo, telefono, email, direccion, 
                   ciudad, notas, created_at, updated_at
            FROM pacientes
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()

        pacientes = []
        for row in rows:
            pacientes.append(
                {
                    "id": row[0],
                    "user_id": row[1],
                    "nombre_completo": row[2],
                    "documento": row[3],
                    "tipo_documento": row[4],
                    "fecha_nacimiento": row[5],
                    "edad": row[6],
                    "sexo": row[7],
                    "telefono": row[8],
                    "email": row[9],
                    "direccion": row[10],
                    "ciudad": row[11],
                    "notas": row[12],
                    "created_at": row[13],
                    "updated_at": row[14],
                }
            )

        return pacientes
    finally:
        cur.close()
        conn.close()


def obtener_paciente(paciente_id: int, user_id: int) -> Optional[dict]:
    """Obtiene un paciente por ID"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT id, user_id, nombre_completo, documento, tipo_documento, 
                   fecha_nacimiento, edad, sexo, telefono, email, direccion, 
                   ciudad, notas, created_at, updated_at
            FROM pacientes
            WHERE id = %s AND user_id = %s
            """,
            (paciente_id, user_id),
        )
        row = cur.fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "user_id": row[1],
            "nombre_completo": row[2],
            "documento": row[3],
            "tipo_documento": row[4],
            "fecha_nacimiento": row[5],
            "edad": row[6],
            "sexo": row[7],
            "telefono": row[8],
            "email": row[9],
            "direccion": row[10],
            "ciudad": row[11],
            "notas": row[12],
            "created_at": row[13],
            "updated_at": row[14],
        }
    finally:
        cur.close()
        conn.close()


def actualizar_paciente(paciente_id: int, data: dict, user_id: int) -> bool:
    """Actualiza un paciente existente"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            UPDATE pacientes
            SET nombre_completo = %s, documento = %s, tipo_documento = %s,
                fecha_nacimiento = %s, edad = %s, sexo = %s, telefono = %s,
                email = %s, direccion = %s, ciudad = %s, notas = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND user_id = %s
            """,
            (
                data.get("nombre_completo"),
                data.get("documento"),
                data.get("tipo_documento"),
                data.get("fecha_nacimiento"),
                data.get("edad"),
                data.get("sexo"),
                data.get("telefono"),
                data.get("email"),
                data.get("direccion"),
                data.get("ciudad"),
                data.get("notas"),
                paciente_id,
                user_id,
            ),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()


def eliminar_paciente(paciente_id: int, user_id: int) -> bool:
    """Elimina un paciente y sus estudios asociados"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            "DELETE FROM pacientes WHERE id = %s AND user_id = %s",
            (paciente_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()


# ============ ESTUDIOS PACIENTE ============


def vincular_estudio(paciente_id: int, data: dict, user_id: int) -> int:
    """Vincula un estudio DICOM a un paciente"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Verificar que el paciente pertenece al usuario
        cur.execute(
            "SELECT id FROM pacientes WHERE id = %s AND user_id = %s",
            (paciente_id, user_id),
        )
        if not cur.fetchone():
            raise ValueError("Paciente no encontrado o no autorizado")

        cur.execute(
            """
            INSERT INTO estudios_paciente 
            (paciente_id, session_id, fecha_estudio, tipo_estudio, diagnostico, notas)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                paciente_id,
                data.get("session_id"),
                data.get("fecha_estudio"),
                data.get("tipo_estudio"),
                data.get("diagnostico"),
                data.get("notas"),
            ),
        )
        estudio_id = cur.fetchone()[0]
        conn.commit()
        return estudio_id
    finally:
        cur.close()
        conn.close()


def listar_estudios_paciente(paciente_id: int, user_id: int) -> List[dict]:
    """Lista todos los estudios de un paciente"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Verificar que el paciente pertenece al usuario
        cur.execute(
            "SELECT id FROM pacientes WHERE id = %s AND user_id = %s",
            (paciente_id, user_id),
        )
        if not cur.fetchone():
            return []

        cur.execute(
            """
            SELECT id, paciente_id, session_id, fecha_estudio, tipo_estudio,
                   diagnostico, notas, created_at
            FROM estudios_paciente
            WHERE paciente_id = %s
            ORDER BY fecha_estudio DESC, created_at DESC
            """,
            (paciente_id,),
        )
        rows = cur.fetchall()

        estudios = []
        for row in rows:
            estudios.append(
                {
                    "id": row[0],
                    "paciente_id": row[1],
                    "session_id": row[2],
                    "fecha_estudio": row[3],
                    "tipo_estudio": row[4],
                    "diagnostico": row[5],
                    "notas": row[6],
                    "created_at": row[7],
                }
            )

        return estudios
    finally:
        cur.close()
        conn.close()


def eliminar_estudio(estudio_id: int, user_id: int) -> bool:
    """Elimina la vinculación de un estudio con un paciente"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Verificar que el estudio pertenece a un paciente del usuario
        cur.execute(
            """
            DELETE FROM estudios_paciente
            WHERE id = %s AND paciente_id IN (
                SELECT id FROM pacientes WHERE user_id = %s
            )
            """,
            (estudio_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()

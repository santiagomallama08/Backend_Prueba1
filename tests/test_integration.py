import pytest
from modules.login.auth_controller import registrar_usuario, verificar_credenciales, obtener_id_usuario
from config.db_config import get_connection

def test_registrar_usuario():
    # Eliminar el usuario si ya existe
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM login_usuarios WHERE email = %s", ('juan@email.com',))
    conn.commit()
    cur.close()
    conn.close()

    # Registrar nuevo usuario
    resultado, mensaje = registrar_usuario('Juan Perez', 'juan@email.com', 'miContraseña123', 'usuario')
    print("Resultado:", resultado)
    print("Mensaje:", mensaje)
    assert resultado == True
    assert mensaje == "Registro exitoso"

def test_login_integration():
    # Eliminar el usuario si ya existe
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM login_usuarios WHERE email = %s", ('carlos@email.com',))
    conn.commit()
    cur.close()
    conn.close()

    # Registrar el usuario necesario para el test
    registrar_usuario('Carlos Gómez', 'carlos@email.com', 'contraseñaSegura123', 'usuario')

    # Verificar que las credenciales funcionen
    assert verificar_credenciales('carlos@email.com', 'contraseñaSegura123') == True

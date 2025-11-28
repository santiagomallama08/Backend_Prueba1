import pytest
from unittest.mock import patch
from modules.login.auth_controller import registrar_usuario, verificar_credenciales


# Test para registrar un usuario (mockeando el acceso a la base de datos)
@patch('modules.login.auth_controller.get_connection')
@patch('modules.login.auth_controller.hash_password', return_value='hashed_pw')
def test_registrar_usuario(mock_hash, mock_conn):
    # Configuramos el mock de la conexión y cursor
    mock_cursor = mock_conn.return_value.cursor.return_value

    resultado, mensaje = registrar_usuario('Juan Perez', 'juan@email.com', 'miContraseña123', 'usuario')

    # Validaciones
    assert resultado is True
    assert mensaje == "Registro exitoso"
    mock_cursor.execute.assert_called_once()


# Test para credenciales correctas (mockeando la base de datos)
@patch('modules.login.auth_controller.get_connection')
@patch('modules.login.auth_controller.verify_password', return_value=True)
def test_verificar_credenciales_correctas(mock_verify, mock_conn):
    mock_cursor = mock_conn.return_value.cursor.return_value
    mock_cursor.fetchone.return_value = ['hashed_pw']

    resultado = verificar_credenciales('juan@email.com', 'miContraseña123')
    assert resultado is True


# Test para credenciales incorrectas
@patch('modules.login.auth_controller.get_connection')
@patch('modules.login.auth_controller.verify_password', return_value=False)
def test_verificar_credenciales_incorrectas(mock_verify, mock_conn):
    mock_cursor = mock_conn.return_value.cursor.return_value
    mock_cursor.fetchone.return_value = ['hashed_pw']

    resultado = verificar_credenciales('juan@email.com', 'contraseñaIncorrecta')
    assert resultado is False

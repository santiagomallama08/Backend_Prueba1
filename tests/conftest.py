import pytest
from unittest import mock  # Agrega esta línea para importar mock
from modules.processing.segmentacion import segmentar_craneo_desde_gui

@pytest.fixture
def dicom_path():
    return "path_to_test_dicom.dcm"

@pytest.fixture
def mock_database():
    # Aquí puedes crear una base de datos simulada si la necesitas para las pruebas
    return mock.MagicMock()

@pytest.fixture
def dicom_viewer_mock():
    # Si necesitas mockear la interfaz gráfica
    return mock.MagicMock()

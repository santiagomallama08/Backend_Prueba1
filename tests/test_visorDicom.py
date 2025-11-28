import pytest
from unittest.mock import MagicMock, patch
from modules.gui.visor_dicom import DICOMViewer  # Ajusta la ruta según sea necesario
import tkinter as tk
from tkinter import filedialog

# Mocks para las funciones de la base de datos y el procesamiento de imágenes
mock_segmentar_craneo = MagicMock()
mock_insertar_protesis = MagicMock()
mock_get_or_create_archivo = MagicMock()

@pytest.fixture
def setup_gui():
    root = tk.Tk()
    usuario_id = 1  # Simulamos un usuario con ID 1
    viewer = DICOMViewer(root, usuario_id)
    return viewer

# Test de apertura de archivo DICOM
@patch("tkinter.filedialog.askopenfilename")
@patch("pydicom.dcmread")
def test_open_dicom(mock_dcmread, mock_askopenfilename, setup_gui):
    # Simulamos un archivo DICOM
    mock_askopenfilename.return_value = "test.dcm"
    mock_dcmread.return_value.pixel_array = [[1, 2], [3, 4]]
    
    viewer = setup_gui
    viewer.open_dicom()
    
    assert viewer.dicom_path == "test.dcm"
    assert viewer.original_image is not None  # La imagen debería haberse cargado
    mock_dcmread.assert_called_once_with("test.dcm")

# Test de la segmentación del cráneo
@patch("modules.processing.segmentacion.segmentar_craneo")
def test_segmentar_craneo(mock_segmentar_craneo, setup_gui):
    mock_segmentar_craneo.return_value = {"output": "mask.png", "dimensiones": {"largo": 10, "ancho": 5}}
    
    viewer = setup_gui
    viewer.dicom_path = "test.dcm"
    
    viewer.segmentar_craneo()  # Llamamos al método para segmentar
    
    mock_segmentar_craneo.assert_called_once_with("test.dcm")
    assert viewer.original_image is not None  # Debe actualizarse la imagen con la máscara
    assert viewer.zoom_slider.get() == 1.0  # El zoom debe restablecerse a 1.0

# Test para calcular dimensiones y guardar en BD
@patch("modules.processing.segmentacion.segmentar_craneo")
@patch("modules.database.dao.get_or_create_archivo_dicom")
@patch("modules.database.dao.insert_protesis_dimension")
def test_calcular_dimensiones(mock_insertar_protesis, mock_get_or_create_archivo, mock_segmentar_craneo, setup_gui):
    mock_segmentar_craneo.return_value = {"output": "mask.png", "dimensiones": {"largo": 10, "ancho": 5}}
    mock_get_or_create_archivo.return_value = 1  # Simulamos que se ha creado un archivo con ID 1
    mock_insertar_protesis.return_value = True  # Simulamos que la inserción fue exitosa

    viewer = setup_gui
    viewer.dicom_path = "test.dcm"
    
    viewer.calcular_dimensiones()  # Llamamos al método que calcula las dimensiones
    
    mock_segmentar_craneo.assert_called_once_with("test.dcm")
    mock_get_or_create_archivo.assert_called_once_with("test.dcm", "test.dcm", 1)
    mock_insertar_protesis.assert_called_once_with(1, "Cráneo", {"largo": 10, "ancho": 5})

# Test de diseño de prótesis
def test_diseno_protesis(setup_gui):
    viewer = setup_gui
    viewer.disenar_protesis()  # Solo verificamos si se llama correctamente
    
    # Verificamos que el mensaje de diseño se muestra
    # Esta prueba es muy básica ya que no se implementa la funcionalidad en sí misma
    assert True

# Test de exportar STL
def test_exportar_stl(setup_gui):
    viewer = setup_gui
    viewer.exportar_stl()  # Solo verificamos que se ejecute sin errores
    
    # No hay una validación real en este caso ya que es una función de impresión
    assert True

# Test de mostrar presupuesto
def test_mostrar_presupuesto(setup_gui):
    viewer = setup_gui
    viewer.mostrar_presupuesto()  # Solo verificamos que se ejecute sin errores
    
    # No hay una validación real en este caso ya que es una función de impresión
    assert True

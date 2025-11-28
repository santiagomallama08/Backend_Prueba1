import pytest
from unittest.mock import patch, MagicMock
from modules.gui.visor_dicom import DICOMViewer
from PIL import Image

@pytest.fixture
def app():
    # Mock completo de tkinter para evitar problemas GUI
    mock_root = MagicMock()
    return DICOMViewer(mock_root, usuario_id=1)

def test_ui_elements_exist(app):
    assert isinstance(app.canvas, MagicMock)  # Ahora es un mock
    assert isinstance(app.zoom_slider, MagicMock)
    assert isinstance(app.rot_slider, MagicMock)

@patch("modules.gui.visor_dicom.filedialog.askopenfilename")
def test_open_dicom_cancel(mock_dialog, app):
    mock_dialog.return_value = ""
    app.open_dicom()
    assert app.dicom_path is None

@patch("modules.gui.visor_dicom.pydicom.dcmread")
@patch("modules.gui.visor_dicom.filedialog.askopenfilename")
def test_open_dicom_success(mock_dialog, mock_dcmread, app):
    mock_dialog.return_value = "test_data/sample.dcm"
    mock_dataset = MagicMock()
    mock_dataset.pixel_array = [[1, 2], [3, 4]]
    mock_dcmread.return_value = mock_dataset

    app.open_dicom()
    assert app.dicom_path == "test_data/sample.dcm"
    assert app.original_image is not None

@patch("modules.gui.visor_dicom.segmentar_craneo")
def test_segmentar_craneo_success(mock_segmentar, app):
    app.dicom_path = "dummy.dcm"
    mock_segmentar.return_value = {"output": "test_data/mask.png"}
    
    with patch("PIL.Image.open", return_value=Image.new("L", (512, 512))):
        app.segmentar_craneo()
        assert app.original_image is not None

@patch("modules.gui.visor_dicom.segmentar_craneo")
def test_segmentar_craneo_error(mock_segmentar, app):
    mock_segmentar.return_value = {"error": "Falló segmentación"}
    app.dicom_path = "dummy.dcm"
    
    with patch("modules.gui.visor_dicom.messagebox.showerror") as mock_error:
        app.segmentar_craneo()
        mock_error.assert_called_once()

@patch("modules.gui.visor_dicom.segmentar_craneo")
@patch("modules.gui.visor_dicom.segmentar_craneo_desde_gui")
@patch("modules.gui.visor_dicom.get_or_create_archivo_dicom")
@patch("modules.gui.visor_dicom.insert_protesis_dimension")
def test_calcular_dimensiones_ok(mock_insert, mock_get, mock_gui, mock_seg, app):
    mock_seg.return_value = {"output": "foo.png", "dimensiones": [1, 2, 3]}
    mock_get.return_value = 123
    app.dicom_path = "dummy.dcm"
    
    app.calcular_dimensiones()
    mock_insert.assert_called_once()
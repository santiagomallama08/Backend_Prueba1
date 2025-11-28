import os
import sys

# Añade el directorio raíz al path (sea cual sea el lugar de ejecución)
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, root_dir)

# Ahora los imports funcionarán desde cualquier ubicación
from modules.gui.visor_dicom import DICOMViewer
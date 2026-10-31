"""Use Clicky's native Windows font, including headless/offscreen previews."""
from pathlib import Path
import os
from PyQt6.QtGui import QFont, QFontDatabase


def ensure_native_font():
    if 'Segoe UI' not in QFontDatabase.families():
        path = Path(os.getenv('WINDIR', 'C:/Windows'))/'Fonts/segoeui.ttf'
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    return QFont('Segoe UI',10)

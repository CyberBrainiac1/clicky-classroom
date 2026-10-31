"""Bundled Lucide outline icons. Loading icons never contacts the network."""
from pathlib import Path
import sys
from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer


def icon(name, color='#9b9da0', size=20):
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    path = root/'assets'/'dashboard-icons'/(name+'.svg')
    if not path.exists():
        return QIcon()
    svg = path.read_text('utf-8').replace('currentColor', color)
    renderer = QSvgRenderer(QByteArray(svg.encode('utf-8')))
    pixels = QPixmap(size*2, size*2)
    pixels.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixels)
    renderer.render(painter)
    painter.end()
    pixels.setDevicePixelRatio(2)
    return QIcon(pixels)

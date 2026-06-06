"""Generate assets/AppIcon.icns — a radar/network sweep glyph."""
import math
import os
import subprocess

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QImage, QPainter, QColor, QBrush, QPen, QLinearGradient, QRadialGradient

ROOT = os.path.dirname(os.path.abspath(__file__))
ICONSET = os.path.join(ROOT, "assets", "AppIcon.iconset")
os.makedirs(ICONSET, exist_ok=True)


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    s = size
    r = s * 0.5

    # rounded squircle background
    grad = QLinearGradient(0, 0, 0, s)
    grad.setColorAt(0, QColor("#1d2740"))
    grad.setColorAt(1, QColor("#0e1320"))
    p.setBrush(QBrush(grad)); p.setPen(Qt.NoPen)
    radius = s * 0.225
    p.drawRoundedRect(QRectF(0, 0, s, s), radius, radius)

    c = QPointF(r, r)
    # concentric radar rings
    pen = QPen(QColor(76, 141, 255, 90)); pen.setWidthF(s * 0.012)
    p.setPen(pen); p.setBrush(Qt.NoBrush)
    for f in (0.62, 0.44, 0.26):
        rad = r * f
        p.drawEllipse(c, rad, rad)

    # sweep wedge
    sweep = QRadialGradient(c, r * 0.62)
    sweep.setColorAt(0, QColor(76, 141, 255, 180))
    sweep.setColorAt(1, QColor(76, 141, 255, 0))
    p.setBrush(QBrush(sweep)); p.setPen(Qt.NoPen)
    p.drawPie(QRectF(c.x() - r * 0.62, c.y() - r * 0.62, r * 1.24, r * 1.24),
              50 * 16, 70 * 16)

    # crosshair lines
    pen = QPen(QColor(76, 141, 255, 70)); pen.setWidthF(s * 0.008)
    p.setPen(pen)
    p.drawLine(QPointF(r, r * 0.32), QPointF(r, r * 1.68))
    p.drawLine(QPointF(r * 0.32, r), QPointF(r * 1.68, r))

    # device blips
    blips = [(0.30, -55, "#3ddc84"), (0.5, 25, "#ffc24c"),
             (0.40, 140, "#4c8dff"), (0.22, -150, "#ff6b6b")]
    for dist, ang, col in blips:
        a = math.radians(ang)
        x = r + math.cos(a) * r * dist
        y = r + math.sin(a) * r * dist
        glow = QRadialGradient(QPointF(x, y), s * 0.06)
        glow.setColorAt(0, QColor(col)); glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(glow)); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(x, y), s * 0.05, s * 0.05)
        p.setBrush(QBrush(QColor(col)))
        p.drawEllipse(QPointF(x, y), s * 0.022, s * 0.022)

    # center hub
    p.setBrush(QBrush(QColor("#eaf1ff"))); p.setPen(Qt.NoPen)
    p.drawEllipse(c, s * 0.03, s * 0.03)
    p.end()
    return img


sizes = [16, 32, 64, 128, 256, 512, 1024]
for base in [16, 32, 128, 256, 512]:
    render(base).save(os.path.join(ICONSET, f"icon_{base}x{base}.png"))
    render(base * 2).save(os.path.join(ICONSET, f"icon_{base}x{base}@2x.png"))

icns = os.path.join(ROOT, "assets", "AppIcon.icns")
try:
    subprocess.run(["iconutil", "-c", "icns", ICONSET, "-o", icns], check=True)
    print("Wrote", icns)
except Exception as e:
    print("iconutil failed:", e)

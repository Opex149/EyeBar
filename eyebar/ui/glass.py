"""Original EyeBar surface renderer: graphite, frost and soft lens-like highlights.

No third-party shaders or reference-project artwork are used. On Windows,
optional system acrylic is enabled separately by services.winapi; this painter
is also a complete graceful fallback on other platforms.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient


GLOW_COLORS = {
    "off": None,
    "ice": (100, 202, 255),
    "mint": (87, 220, 175),
    "lilac": (175, 137, 255),
    "amber": (255, 191, 110),
}


def _clamp(value, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (ValueError, TypeError, OverflowError):
        return hi


def paint_surface(p: QPainter, area: QRectF, cfg, radius: float,
                  phase: float = 0.0, pointer: QPointF | None = None) -> None:
    """Paint the same EyeBar silhouette with a configurable material.

    `cfg` is either Config or an unsaved preview dict, both providing get().
    The acrylic blur behind the window is a Windows OS feature and cannot be
    demonstrated in the preview; the tint and highlights render everywhere.
    """
    if area.width() <= 0 or area.height() <= 0:
        return
    mode = str(cfg.get("glass_mode") or "classic")
    if mode not in ("classic", "frosted", "liquid"):
        mode = "classic"
    opacity = _clamp(cfg.get("glass_opacity"), 40, 100) / 100.0
    tint = _clamp(cfg.get("glass_tint"), 20, 100) / 100.0
    light = bool(cfg.get("glass_lite"))
    glow = GLOW_COLORS.get(str(cfg.get("glass_glow") or "off"))
    if light:
        phase = 0.0

    path = QPainterPath()
    path.addRoundedRect(area, radius, radius)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    if mode == "classic":
        p.fillPath(path, QColor(18, 18, 21, round(238 * opacity)))
        stroke = QColor(255, 255, 255, 22)
    else:
        # Transparent graphite base, then an original softly lit matte glaze.
        # Acrylic is requested from Windows; on unsupported systems this
        # remains a decorative translucent material rather than fake blur.
        base_alpha = round((88 + 118 * tint) * opacity)
        p.fillPath(path, QColor(17, 22, 31, base_alpha))
        p.setClipPath(path)
        fill = QLinearGradient(area.topLeft(), area.bottomRight())
        if mode == "liquid":
            fill.setColorAt(0.0, QColor(225, 244, 255, round(47 * opacity)))
            fill.setColorAt(0.33, QColor(105, 133, 159, round(18 * opacity)))
            fill.setColorAt(0.68, QColor(25, 32, 47, round(42 * opacity)))
            fill.setColorAt(1.0, QColor(192, 226, 255, round(18 * opacity)))
        else:
            fill.setColorAt(0.0, QColor(236, 244, 255, round(26 * opacity)))
            fill.setColorAt(1.0, QColor(30, 43, 62, round(26 * opacity)))
        p.fillPath(path, QBrush(fill))
        if mode == "liquid" and not light:
            x = (pointer.x() if pointer is not None else area.center().x() +
                 math.sin(phase) * area.width() * 0.28)
            y = (pointer.y() if pointer is not None else area.top() + area.height() * .22)
            halo = QRadialGradient(QPointF(x, y), max(48.0, area.width() * .65))
            halo.setColorAt(0, QColor(215, 238, 255, round(30 * opacity)))
            halo.setColorAt(1, QColor(215, 238, 255, 0))
            p.fillPath(path, QBrush(halo))
        p.setClipping(False)
        stroke = QColor(238, 248, 255, 55 if mode == "liquid" else 40)

    if glow and not light:
        # Edge light is a quiet EyeBar accent, never a new floating island.
        cx = area.left() + area.width() * (.5 + math.sin(phase) * .29)
        cy = area.bottom() - 3
        halo = QRadialGradient(QPointF(cx, cy), area.width() * .76)
        halo.setColorAt(0, QColor(*glow, 50 if mode != "classic" else 32))
        halo.setColorAt(1, QColor(*glow, 0))
        p.setClipPath(path)
        p.fillPath(path, QBrush(halo))
        p.setClipping(False)

    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(stroke, 1.0))
    p.drawRoundedRect(area, radius, radius)

    if mode == "liquid" and not light:
        # Fine illuminated upper rim (lens *appearance*, no pixel refraction).
        inner = area.adjusted(2.5, 2.5, -2.5, -2.5)
        rim = QLinearGradient(inner.topLeft(), inner.topRight())
        rim.setColorAt(0, QColor(83, 212, 255, 18))
        rim.setColorAt(.52, QColor(242, 251, 255, 90))
        rim.setColorAt(1, QColor(193, 137, 255, 25))
        p.setPen(QPen(QBrush(rim), 1.1))
        p.drawRoundedRect(inner, max(1, radius - 2.5), max(1, radius - 2.5))
    p.restore()

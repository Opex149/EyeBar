"""Validate the real StandBy window at the current Qt device-pixel ratio.

Run once for each external QT_SCALE_FACTOR. No weather requests, media session
polling, demo temperatures, or invented track metadata are used. The snapshots
exercise the real empty/offline states in a temporary, isolated configuration.

Example (Windows cmd.exe):
    set QT_QPA_PLATFORM=offscreen
    set QT_SCALE_FACTOR=1.25
    py tools/check_display_matrix.py --outputJSON matrix-125.json --screenshotsDIR captures

Offscreen geometry checks do not certify native Windows mixed-monitor DPI.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import traceback
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
RESOLUTIONS = ((1920, 1080), (2560, 1440), (3840, 2160))
PROFILES = ("classic", "minimal", "dashboard")
POSITIONS = ("left", "center", "right")
CARDS = ("weather", "music", "timer", "notes")


def validate(output: Path, screenshots: Path | None = None) -> list[dict]:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT))

    from PyQt6.QtCore import QPoint, QRect
    from PyQt6.QtWidgets import QApplication, QWidget
    from eyebar.app import Controller
    from eyebar.config import Config
    from eyebar.ui.theme import STYLE

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)
    records: list[dict] = []
    callback_errors: list[str] = []
    old_excepthook = sys.excepthook

    def report_callback_error(exc_type, exc, tb):
        callback_errors.append("".join(traceback.format_exception(exc_type, exc, tb)))
        traceback.print_exception(exc_type, exc, tb)

    sys.excepthook = report_callback_error

    def assert_inside(widget, container, context: str) -> None:
        if not widget.isVisible():
            return  # Hidden profiles intentionally keep their previous geometry.
        rect = QRect(widget.mapTo(container, QPoint()), widget.size())
        name = widget.objectName() or type(widget).__name__
        assert container.rect().contains(rect), (
            f"{context}: {name} {rect} lies outside {container.rect()}"
        )

    controller = None
    try:
        with tempfile.TemporaryDirectory(prefix="eyebar-display-") as temporary:
            config_path = Path(temporary) / "config.json"
            config = Config(config_path)
            notes = "Проверка сохранности заметок\nEyeBar 1.1 · кириллица"
            config.data.update(
                mascot="classic_blue", decorative_animations=False,
                animation_intensity=0, standby_autohide=False,
                standby_cards=list(CARDS), brightness=100, notes=notes,
            )
            assert config.save(), "Could not write isolated validation config"
            original_preferences = {key: deepcopy(config.get(key)) for key in (
                "notes", "standby_cards", "mascot_scale", "outline_color",
                "backlight_brightness", "brightness", "mascot",
            )}

            # Construct the actual controller and widgets, while avoiding live
            # HTTP/media services and any writes to the user's configuration.
            with patch("eyebar.app.Config", return_value=config), \
                 patch("eyebar.services.weather.WeatherService.refresh"), \
                 patch("eyebar.services.media._load_winrt", return_value=None), \
                 patch("eyebar.services.media.MediaService.start"):
                controller = Controller(app)
                window = controller.standby
                # Deliver a genuine service error state, with no sample data.
                controller.weather._on_done(
                    str(config.get("city")).strip(), None, "weather.error_network",
                )
                assert controller.weather.last is None
                assert not controller.media.info.title
                assert not controller.media.info.artist
                window.apply_settings()
                dpr = float(window.devicePixelRatioF())
                assert dpr > 0, "Qt did not report a valid device-pixel ratio"

                for physical_width, physical_height in RESOLUTIONS:
                    width = round(physical_width / dpr)
                    height = round(physical_height / dpr)
                    for profile in PROFILES:
                        for position in POSITIONS:
                            context = f"{physical_width}x{physical_height}, DPR={dpr:g}, {profile}/{position}"
                            config.set("standby_profile", profile, save=False)
                            config.set("standby_mascot_position", position, save=False)
                            window.apply_settings()
                            window.resize(width, height)
                            window.show()
                            app.processEvents()
                            # A second layout pass resolves nested card layouts
                            # after a previous profile's visibility was changed.
                            app.processEvents()
                            assert not callback_errors, callback_errors[0] if callback_errors else ""
                            assert window.width() == width and window.height() == height, (
                                f"{context}: unexpected logical size {window.size()}"
                            )
                            actual_dpr = float(window.devicePixelRatioF())
                            assert abs(actual_dpr - dpr) < 0.001, (
                                f"{context}: DPR changed unexpectedly to {actual_dpr}"
                            )

                            for widget in (
                                window.clock, window.date, window.mascot,
                                window.bottom, window.bright_w, window.slider,
                                window.btn_alarm, window.btn_night, window.btn_settings,
                                window.dashboard_status,
                            ):
                                assert_inside(widget, window, context)
                            assert window.clock.isVisible(), f"{context}: clock hidden"
                            assert window.date.isVisible(), f"{context}: date hidden"
                            assert window.clock.fontMetrics().horizontalAdvance(
                                window.clock.text()) <= window.clock.width(), (
                                    f"{context}: clock text is clipped"
                                )
                            assert window.mascot.isVisible() == (profile != "minimal"), (
                                f"{context}: wrong mascot visibility"
                            )
                            assert window.dashboard_status.isVisible() == (profile == "dashboard"), (
                                f"{context}: wrong dashboard status visibility"
                            )
                            for name, card in window._card_map.items():
                                assert card.isVisible() == (profile != "minimal"), (
                                    f"{context}: wrong {name} card visibility"
                                )
                                if not card.isVisible():
                                    continue
                                assert_inside(card, window, context)
                                for field in card.findChildren(QWidget):
                                    assert_inside(field, card, context + "/" + name)

                            expected_index = POSITIONS.index(position)
                            assert window.body.itemAt(expected_index).widget() is window.mascot, (
                                f"{context}: saved character position was not applied"
                            )
                            for key, expected in original_preferences.items():
                                assert config.get(key) == expected, (
                                    f"{context}: profile switch changed {key}"
                                )
                            assert window.notes.toPlainText() == notes, (
                                f"{context}: note text changed while switching profiles"
                            )

                            # A QWidget can be geometrically visible while an
                            # opacity-effect cache paints it transparent. Check
                            # real pixels of the Settings icon in the full-window
                            # render, rather than trusting isVisible() alone.
                            frame = window.grab()
                            assert not frame.isNull(), f"{context}: empty window render"
                            rendered = frame.toImage()
                            nav_rect = QRect(window.btn_settings.mapTo(window, QPoint()),
                                             window.btn_settings.size())
                            bright_pixels = 0
                            for y in range(math.floor(nav_rect.top() * actual_dpr),
                                           math.ceil((nav_rect.bottom() + 1) * actual_dpr)):
                                for x in range(math.floor(nav_rect.left() * actual_dpr),
                                               math.ceil((nav_rect.right() + 1) * actual_dpr)):
                                    color = rendered.pixelColor(x, y)
                                    if color.alpha() > 0 and max(color.red(), color.green(), color.blue()) > 110:
                                        bright_pixels += 1
                            assert bright_pixels >= 5, (
                                f"{context}: Settings icon is transparent despite visible geometry"
                            )

                            record = dict(
                                physical=[physical_width, physical_height],
                                logical=[width, height], dpr=actual_dpr,
                                qt_scale_factor=os.environ.get("QT_SCALE_FACTOR", "auto"),
                                profile=profile, position=position, status="passed",
                                weather_state="offline_without_sample_data",
                                media_state="backend_disabled_without_sample_metadata",
                                navigation_pixels="passed",
                            )
                            if screenshots is not None and physical_width == 1920 and position == "center":
                                screenshots.mkdir(parents=True, exist_ok=True)
                                tag = f"{dpr * 100:g}".replace(".", "_")
                                capture = screenshots / f"StandBy_{profile}_{tag}.png"
                                assert frame.save(str(capture)), (
                                    f"{context}: screenshot could not be saved"
                                )
                                record["screenshot"] = str(capture.resolve())
                            records.append(record)
                            window.hide()

                assert config.save(), "Could not save final validation config"
                reopened = Config(config_path)
                for key, expected in original_preferences.items():
                    assert reopened.get(key) == expected, f"Restart changed {key}"
                controller.timer.stop()
                controller._cleanup()
                controller.minibar.close()
                window.close()
                app.processEvents()
                controller = None
            assert not callback_errors, callback_errors[0] if callback_errors else ""
    finally:
        if controller is not None:
            controller.timer.stop()
            controller._cleanup()
            controller.minibar.close()
            controller.standby.close()
            app.processEvents()
        sys.excepthook = old_excepthook

    assert len(records) == 27, f"Expected 27 cases, got {len(records)}"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--outputJSON", "--output-json", dest="output", type=Path,
                        required=True, help="JSON output for this process's observed DPR")
    parser.add_argument("--screenshotsDIR", "--screenshots-dir", dest="screenshots", type=Path,
                        help="Optional directory for honest Full HD profile snapshots")
    arguments = parser.parse_args()
    records = validate(arguments.output, arguments.screenshots)
    print(json.dumps(dict(cases=len(records), dpr=records[0]["dpr"],
                          output=str(arguments.output.resolve()),
                          screenshots=[case["screenshot"] for case in records if "screenshot" in case])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

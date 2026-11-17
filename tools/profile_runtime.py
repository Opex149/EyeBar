#!/usr/bin/env python3
"""Measure EyeBar's real Qt UI process with isolated, disposable settings.

Run each scenario in a fresh process, for example::

    python tools/profile_runtime.py --duration 30 --scenario idle --output idle.json
    python tools/profile_runtime.py --duration 30 --scenario disabled --output disabled.json
    python tools/profile_runtime.py --duration 30 --scenario switching --output switching.json

This is a UI-only benchmark, not a measurement of weather HTTP, Windows media
integration, audio, or native global hotkeys. Those external operations are
explicitly disabled. CPU uses process_time / monotonic elapsed time (100% means
one CPU core). Linux memory is current RSS from /proc/self/statm. The optional
resource fallback is labelled peak RSS, never presented as current memory.
Results include profiling overhead and apply only to the reported host and Qt
platform. Offscreen/Xvfb Linux results do not establish Windows performance,
actual Windows DPI behavior, GPU/compositor cost, or long-term leak freedom.
Qt inventories count QTimer/QAbstractAnimation objects reachable from the real
controller and known windows; internal Qt timers are outside that inventory.
No psutil or other profiling dependency is required.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

# Permit invocation from any working directory without installing the package.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def memory_sample() -> dict:
    """Return bytes plus an explicit current/peak/unavailable classification."""
    if sys.platform.startswith("linux"):
        try:
            resident_pages = int(Path("/proc/self/statm").read_text().split()[1])
            return {"bytes": resident_pages * os.sysconf("SC_PAGE_SIZE"),
                    "kind": "current_rss", "source": "/proc/self/statm"}
        except (OSError, ValueError, IndexError):
            pass
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                    (name, ctypes.c_size_t) for name in (
                        "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                        "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                        "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE,
                                                   ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
                return {"bytes": int(counters.WorkingSetSize), "kind": "current_rss",
                        "source": "Windows GetProcessMemoryInfo.WorkingSetSize"}
        except (OSError, AttributeError):
            pass
    try:
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return {"bytes": int(value if sys.platform == "darwin" else value * 1024),
                "kind": "peak_rss", "source": "resource.getrusage.ru_maxrss"}
    except (ImportError, OSError, AttributeError):
        return {"bytes": None, "kind": "unavailable", "source": None}


def qt_inventory(root) -> dict:
    """Count parent-owned application objects without retaining their wrappers."""
    from PyQt6.QtCore import QAbstractAnimation, QTimer
    timers = root.findChildren(QTimer)
    active = [timer for timer in timers if timer.isActive()]
    animations = root.findChildren(QAbstractAnimation)
    return {
        "class": type(root).__name__,
        "visible": root.isVisible() if hasattr(root, "isVisible") else None,
        "qtimers_total": len(timers),
        "qtimers_active": len(active),
        "active_timer_intervals_ms": dict(sorted(Counter(str(t.interval()) for t in active).items())),
        "qabstractanimations_total": len(animations),
        "qabstractanimations_running": sum(
            a.state() == QAbstractAnimation.State.Running for a in animations),
    }


def numeric_summary(values: list[float]) -> dict:
    if not values:
        return {"min": None, "max": None, "mean": None, "median": None}
    return {"min": min(values), "max": max(values),
            "mean": statistics.fmean(values), "median": statistics.median(values)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--duration", type=float, default=30, help="Measured seconds after a fixed 2s warm-up")
    parser.add_argument("--scenario", choices=("idle", "disabled", "switching"), default="idle")
    parser.add_argument("--output", type=Path, required=True, help="Destination JSON report")
    args = parser.parse_args(argv)
    if not math.isfinite(args.duration) or args.duration <= 0 or args.duration > 86400:
        parser.error("--duration must be greater than zero and at most 86400 seconds")
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PyQt6.QtCore import QTimer, Qt, QT_VERSION_STR, PYQT_VERSION_STR
    from PyQt6.QtWidgets import QApplication
    from eyebar.app import Controller
    from eyebar.config import Config
    from eyebar.ui.theme import STYLE, app_icon

    app = QApplication([sys.argv[0]])
    app.setApplicationName("EyeBar Runtime Profile")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)
    app.setWindowIcon(app_icon())
    report = {
        "schema_version": 1,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "scenario": args.scenario,
        "requested_duration_seconds": args.duration,
        "warmup_seconds": 2.0,
        "host": {"system": platform.system(), "release": platform.release(),
                 "machine": platform.machine(), "python": platform.python_version(),
                 "qt": QT_VERSION_STR, "pyqt": PYQT_VERSION_STR,
                 "qt_platform": app.platformName(), "logical_cpu_count": os.cpu_count(),
                 "screens": [{"width": s.geometry().width(), "height": s.geometry().height(),
                              "device_pixel_ratio": s.devicePixelRatio(), "logical_dpi": s.logicalDotsPerInch()}
                             for s in app.screens()]},
        "scope": {
            "ui_only": True, "real_controller_and_stylesheet": True,
            "weather_refresh_disabled": True, "http_transport_blocked": True,
            "windows_media_backend_disabled": True, "media_polling_disabled": True,
            "global_hotkey_registration_disabled": True, "temporary_user_config": True,
            "single_core_cpu_percent": True, "sample_interval_seconds": 1.0,
            "switch_action_interval_seconds": 1.0 if args.scenario == "switching" else None,
            "limitations": ["Host-specific UI process measurements, including profiling overhead.",
                            "No external weather/media workload, audio or real global hotkeys.",
                            "Qt inventory excludes internal timers and unparented objects.",
                            "Short profiling cannot establish absence of long-term memory leaks.",
                            "Linux/offscreen/Xvfb measurements do not validate Windows performance or DPI."],
        },
        "samples": [], "switch_actions": [], "errors": [],
    }
    old_exception_hook = sys.excepthook

    def exception_hook(kind, value, traceback):
        report["errors"].append(f"{kind.__name__}: {value}")
        old_exception_hook(kind, value, traceback)
        app.exit(1)

    sys.excepthook = exception_hook
    try:
        with tempfile.TemporaryDirectory(prefix="eyebar-profile-") as temporary, ExitStack() as patches:
            config = Config(Path(temporary) / "config.json")
            config.data.update(mascot="classic_blue", classic_blue_default=False,
                               idle_minutes=0, night_auto=False, night_power_enabled=False,
                               glass_mode="classic", bar_collapsed=False, alarms=[])
            if args.scenario == "disabled":
                config.data.update(decorative_animations=False, animation_intensity=0)
            patches.enter_context(patch("eyebar.app.Config", return_value=config))
            suppressed_refreshes = patches.enter_context(patch("eyebar.services.weather.WeatherService.refresh"))
            blocked_http = patches.enter_context(patch("urllib.request.urlopen", side_effect=RuntimeError("Profiler blocks HTTP")))
            patches.enter_context(patch("eyebar.services.media._load_winrt", return_value=None))
            patches.enter_context(patch("eyebar.services.media.MediaService.start"))
            patches.enter_context(patch("eyebar.services.winapi.GlobalHotkey.register", return_value=False))
            patches.enter_context(patch("eyebar.services.winapi.GlobalHotkey.unregister"))
            controller = Controller(app)
            controller.start()
            controller.minibar.show()
            controller.minibar.raise_()
            measurement = {}
            sample_timer = QTimer(app)
            action_timer = QTimer(app)
            finish_timer = QTimer(app)
            warmup_timer = QTimer(app)
            warmup_timer.setSingleShot(True)
            for profiler_timer in (sample_timer, action_timer, finish_timer, warmup_timer):
                profiler_timer.setTimerType(Qt.TimerType.PreciseTimer)
            finish_timer.setSingleShot(True)

            def roots():
                result = {"controller_services": controller, "minibar": controller.minibar,
                          "standby": controller.standby}
                if controller.settings_dialog is not None:
                    result["settings"] = controller.settings_dialog
                if controller.minibar._notes is not None:
                    result["notes"] = controller.minibar._notes
                if controller.alarm_dialog is not None:
                    result["alarms"] = controller.alarm_dialog
                return result

            def sample():
                wall, cpu = time.monotonic(), time.process_time()
                previous_wall = measurement.get("previous_wall", measurement["wall"])
                previous_cpu = measurement.get("previous_cpu", measurement["cpu"])
                elapsed = wall - previous_wall
                report["samples"].append({
                    "elapsed_seconds": wall - measurement["wall"],
                    "process_cpu_seconds": cpu - measurement["cpu"],
                    "interval_cpu_percent_one_core": 100 * (cpu - previous_cpu) / elapsed if elapsed > 0.01 else None,
                    "memory": memory_sample(),
                    "qt": {name: qt_inventory(root) for name, root in roots().items()},
                })
                measurement["previous_wall"], measurement["previous_cpu"] = wall, cpu

            def switch_action():
                index = measurement["actions"]
                phase, cycle = index % 6, index // 6
                mascots = tuple(controller.mascots)
                if phase == 0:
                    controller.exit_standby()
                    controller.minibar.set_collapsed(True, animate=True)
                    action = "cube"
                elif phase == 1:
                    controller.minibar.set_collapsed(False, animate=True)
                    action = "full_bar"
                elif phase in (2, 3, 4):
                    profile = ("classic", "minimal", "dashboard")[phase - 2]
                    config.set("standby_profile", profile, save=False)
                    controller.standby.apply_settings()
                    controller.enter_standby()
                    action = "standby_" + profile
                else:
                    controller.exit_standby()
                    theme = ("classic", "frosted", "liquid")[cycle % 3]
                    config.set("glass_mode", theme, save=False)
                    controller.set_mascot(mascots[cycle % len(mascots)], save=False)
                    action = f"theme_{theme}_mascot_{controller.current_mascot().id}"
                report["switch_actions"].append({"elapsed_seconds": time.monotonic() - measurement["wall"],
                                                 "action": action})
                measurement["actions"] += 1

            def finish():
                sample_timer.stop()
                action_timer.stop()
                sample()
                elapsed = time.monotonic() - measurement["wall"]
                cpu = time.process_time() - measurement["cpu"]
                memory_values = [s["memory"]["bytes"] for s in report["samples"] if s["memory"]["bytes"] is not None]
                report["results"] = {
                    "elapsed_seconds": elapsed, "process_cpu_seconds": cpu,
                    "cpu_percent_one_core": 100 * cpu / elapsed,
                    "interval_cpu_percent_one_core": numeric_summary(
                        [s["interval_cpu_percent_one_core"] for s in report["samples"]
                         if s["interval_cpu_percent_one_core"] is not None]),
                    "memory_bytes": numeric_summary(memory_values),
                    "memory_sources": sorted({s["memory"]["source"] for s in report["samples"] if s["memory"]["source"]}),
                    "memory_kinds": sorted({s["memory"]["kind"] for s in report["samples"]}),
                    "weather_refresh_calls_suppressed": suppressed_refreshes.call_count,
                    "http_calls_blocked": blocked_http.call_count,
                    "switch_actions_completed": measurement["actions"],
                }
                app.quit()

            def begin():
                measurement.update(wall=time.monotonic(), cpu=time.process_time(), actions=0)
                sample()
                sample_timer.timeout.connect(sample)
                sample_timer.start(1000)
                if args.scenario == "switching":
                    switch_action()
                    action_timer.timeout.connect(switch_action)
                    action_timer.start(1000)
                finish_timer.timeout.connect(finish)
                finish_timer.start(round(args.duration * 1000))

            warmup_timer.timeout.connect(begin)
            warmup_timer.start(2000)
            exit_code = app.exec()
            controller.minibar.hide()
            controller.standby.hide()
            controller.timer.stop()
            if "results" not in report:
                report["errors"].append("Profiling ended before the measurement completed")
            report["finished_utc"] = datetime.now(timezone.utc).isoformat()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"output": str(args.output.resolve()), "scenario": args.scenario,
                              "results": report.get("results"), "errors": report["errors"]}, ensure_ascii=False))
            return exit_code if exit_code else (1 if report["errors"] else 0)
    finally:
        sys.excepthook = old_exception_hook


if __name__ == "__main__":
    raise SystemExit(main())

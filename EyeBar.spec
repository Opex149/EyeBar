# -*- mode: python ; coding: utf-8 -*-
"""Build with: python -m PyInstaller --clean --noconfirm EyeBar.spec"""
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

project = Path(SPECPATH)
datas = [(str(project / "locales"), "locales")]
if (project / "assets").is_dir():
    datas.append((str(project / "assets"), "assets"))

# Include any non-Python files supplied with mascot packages (if present).
for package in ("eyebar.mascots.cyber_cat", "eyebar.mascots.neon_ghost", "eyebar.mascots.luna_bunny", "eyebar.mascots.byte_fox"):
    datas += collect_data_files(package)

hiddenimports = [
    "eyebar.mascots.cyber_cat",
    "eyebar.mascots.cyber_cat.cat",
    "eyebar.mascots.neon_ghost",
    "eyebar.mascots.neon_ghost.ghost",
    "eyebar.mascots.luna_bunny",
    "eyebar.mascots.luna_bunny.bunny",
    "eyebar.mascots.byte_fox",
    "eyebar.mascots.byte_fox.fox",
]
# media.py loads these via importlib; they are optional on systems without
# Windows Runtime packages. Include their installed submodules when present.
for package in (
    "winrt.windows.media.control",
    "winrt.windows.storage.streams",
    "winsdk.windows.media.control",
    "winsdk.windows.storage.streams",
):
    hiddenimports += collect_submodules(package, on_error="ignore")

a = Analysis(
    [str(project / "main.py")],
    pathex=[str(project)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="EyeBar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,       # --windowed
    disable_windowed_traceback=False,
)

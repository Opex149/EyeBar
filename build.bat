@echo off
setlocal
cd /d "%~dp0"
py -m pip install -r requirements.txt
if errorlevel 1 goto :error
rem Optional Windows media metadata. A missing wheel must not block the EXE build.
py -m pip install -r requirements-media.txt
if errorlevel 1 echo WARNING: optional Windows media backend is unavailable. Building EyeBar anyway.
py -m pip install --upgrade pyinstaller
if errorlevel 1 goto :error
py -m compileall -q eyebar main.py
if errorlevel 1 goto :error
py -m PyInstaller --clean --noconfirm EyeBar.spec
if errorlevel 1 goto :error
echo.
echo Built: "%CD%\dist\EyeBar.exe"
exit /b 0
:error
echo ERROR: Build failed. Read the output above.
exit /b 1

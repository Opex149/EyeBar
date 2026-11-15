# EyeBar v3 — Prelaunch Major Update

## Main changes
- Fully redrawn Cyber Cat: sitting pose, fluffier silhouette, more detailed face, temperature stitching on fur.
- New built-in mascots: Luna Bunny and Byte Fox.
- Mini cube updated: mascot centered better, separate weather icon removed.
- Current temperature is shown on the mascot itself as an embroidered patch.
- Larger built-in list of Russian cities for weather selection in Settings.
- PyInstaller spec updated for all built-in mascots.

## Technical fixes
- Added mascot temperature state propagation from weather service.
- Removed stale mini-cube weather badge references.
- Verified Python syntax and translations.
- 17 tests passed (3 GUI smoke tests skipped in this environment).

## Build
Use `build.bat` or:

```bat
py -m pip install -r requirements.txt
py -m pip install --upgrade pyinstaller
py -m PyInstaller --clean --noconfirm EyeBar.spec
```

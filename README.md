# EyeBar v3.0

Установка и запуск (Windows 10/11, Python 3.10+):

    pip install -r requirements.txt
    python main.py

Необязательные пакеты для плеера Windows (название, исполнитель, обложка) находятся в requirements-media.txt:
winrt-runtime, winrt-Windows.Foundation, winrt-Windows.Foundation.Collections,
winrt-Windows.Storage.Streams, winrt-Windows.Media.Control.
Если они не установились (например, нет колёс под вашу версию Python), поставьте `pip install winsdk`
(Python до 3.12) — приложение подхватит его автоматически. Без них всё работает, но кнопки
плеера отправляют обычные медиаклавиши, а название трека не показывается.

Что нового в v3.0:
- Настройки и все кнопки: окно «поверх всех», безопасное открытие, глобальный перехват ошибок
  (лог: %APPDATA%\EyeBar\eyebar.log)
- Плеер Windows (GSMTC): трек, исполнитель, обложка, play/pause/next/prev
- Мини-бар справа у края экрана + режим «кубик» (кнопка в панели и в кубике, клик по кубику)
- Эмоции: Обычный, Радость/музыка, Злость, Сонный (проверка в настройках; музыка радует кота сама)
- Погодные реакции по реальной погоде: дождь — 60% зонт / 40% мокнет и злится;
  сильный ветер — 95% трепещут усы, шерсть и хвост / 5% сдувает за край экрана

Проверка пасхалок без ожидания погоды (в настройках их нет — только по реальной погоде):

    python main.py --sim-weather=umbrella
    python main.py --sim-weather=wet
    python main.py --sim-weather=wind
    python main.py --sim-weather=blow

Настройки: %APPDATA%\EyeBar\config.json

Установка `requirements-media.txt` необязательна: при её неудаче можно сразу
собрать EXE; музыка при этом управляется системными медиаклавишами.

## Single-file Windows executable (PyInstaller)

Build **on Windows 10/11** with Python 3.10+ (recommended: a supported
Python version with wheels for all packages). Open Command Prompt in the
project folder and run:

```bat
py -m pip install -r requirements.txt
py -m pip install -r requirements-media.txt
py -m pip install --upgrade pyinstaller
py -m PyInstaller --clean --noconfirm EyeBar.spec
```

Or run `build.bat`. Output: `dist\EyeBar.exe`. The spec makes a **single-file,
windowed** executable (equivalent to `--onefile --windowed`); do **not**
append those command-line flags when building from a `.spec` file.

Alternatively, for a direct command without the spec:

```bat
py -m PyInstaller --clean --noconfirm --onefile --windowed --name EyeBar --add-data "locales;locales" --hidden-import eyebar.mascots.cyber_cat --hidden-import eyebar.mascots.neon_ghost main.py
```

The direct command does not automatically include optional `assets/` or
media-backend dynamic imports; use `EyeBar.spec` for the complete build.
PyInstaller cannot cross-compile a Windows `.exe` from Linux/macOS.
Bundled locales and optional `assets/` are read from `sys._MEIPASS`;
config and logs stay in `%APPDATA%\EyeBar`.

If the Settings window fails to initialize, EyeBar now displays the exception
in a message box and logs it to `%APPDATA%\EyeBar\eyebar.log`.

## EyeBar appearance controls (original interface, no Dynamic Island)

The default is **Original graphite**: the familiar right-hand mini-bar and
collapsible cube are unchanged, as are the two original mascots and StandBy.
The reference application was used only as inspiration for the *settings
ideas*. Its code, layout, illustrations, shaders, and assets are not included.

Open the **gear icon → Mini-bar appearance** section. Here you can:

- Choose **Original graphite**, **Frosted glass**, or **Liquid glass**.
  Glass styles use an original translucent graphite surface and delicate edge
  highlights. On Windows 10/11, EyeBar also *requests* system acrylic/blur;
  Windows may decline it or render it differently. There is **no pixel-level
  refraction or identical Liquid Glass shader** in this version.
- Adjust opacity (40–100%), glass tint (20–100%), edge glow (off / four colors),
  and enable/disable moving highlights and the cube transition.
- Enable **Lightweight graphics** to disable native blur and dynamic lighting.
- Set the full bar width (280–360 px), lock its dragged position, or request
  Windows screen-capture exclusion for the mini-bar (best effort; not a
  reliable security/privacy boundary for all capture software).
- Preview changes before saving. **Restore original look** resets the new
  appearance controls only, and requires **Save** to apply.

All options are saved to `%APPDATA%\EyeBar\config.json`; the base Python app and
PyInstaller one-file build use the same options. Existing user settings are
preserved with new defaults added. No external dependencies were added.

If opening Settings fails, the exception appears in a message box and in
`%APPDATA%\EyeBar\eyebar.log`.

## Исправления стабильности (Bugfix audit)

- Настройки: повторное открытие и восстановление свёрнутого окна, видимые ошибки запуска;
  «Отмена» теперь действительно откатывает предварительный выбор персонажа.
- Конфигурация: нормализация повреждённых полей, безопасная атомарная запись,
  предупреждение при ошибке сохранения, проверка поддерживаемой горячей клавиши.
- Погода: сетевой запрос в daemon-потоке без потенциального падения QThread при выходе,
  отбрасывание устаревшего результата при смене города.
- StandBy/трей: команда «Показать» корректно выходит из StandBy, пауза перед
  повторной активацией по простоям, восстановление после прерванного пролёта персонажа.
- Заметки: синхронизация содержимого между окном заметок и StandBy при активации,
  сохранение при завершении приложения.
- Анимации: более устойчивое переключение кубика/панели при прерывании анимации.
- Сборка: необязательные пакеты winrt не блокируют сборку однофайлового EXE.

### Проверки

Из корня проекта:

```bat
py -m compileall -q eyebar main.py
py -m unittest discover -s tests -v
```

Для GUI-проверок нужен PyQt6; тесты с Qt помечаются как пропущенные, если он не
установлен. Команды сборки и GUI-тесты следует запускать на Windows: Linux
не может создать/запустить проверенный Windows `.exe` через PyInstaller.

## EyeBar Emotion & Widgets Edition

The original mini-bar and cube remain the default interface. Settings now include:

- **Emotions:** select a persistent emotion (normal, happy, angry, sleepy, curious,
  surprised, love, sad, dancing). The selection is stored in `config.json` when
  **Save** is pressed. Music automatically triggers dancing when the configured
  emotion is normal; rain can temporarily override with an angry expression.
- **Music accessories:** randomly choose wireless earbuds or over-ear headphones
  with a 50/50 probability once when playback begins. You can also select one
  type permanently or disable accessories. No sound-device detection is implied.
- **Eye tracking:** disabled during sleepy, angry, or sad moods, and can be
  switched off globally in Settings.
- **Weather demo:** preview umbrella, rain, wind, and clear weather in Settings.
  Real reactions still use the Weather service; the demo does not change it.
- **Widgets:** show/hide and reorder the mini-bar's weather/mascot block, track
  details, media controls, launcher row, and custom buttons. Reordering is by
  drag and drop or the arrow buttons. Original StandBy layout is unchanged.
- **Custom command buttons:** supply a label and a local executable/command
  (optionally with arguments). These launch **only on click** with `shell=False`.
  Only add commands you trust; the user is responsible for the command's effects.

Run automated non-GUI checks via `python -m unittest discover -s tests -v`.
GUI tests and Windows PyInstaller output must be checked on Windows with PyQt6.

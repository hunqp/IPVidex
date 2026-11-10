# Development

## Run from source

Requires Windows 64-bit, Python 3.10+ and 64-bit VLC 3.x.

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv\Scripts\python.exe main.py
```

## Structure

| Path | Contents |
|---|---|
| `core/` | Settings, paths, version, error handling |
| `infrastructure/` | ONVIF, RTSP, TLS relay, worker processes, MediaMTX |
| `services/` | ONVIF device operations |
| `gui/`, `gui/pages/` | Windows, tabs and device pages |
| `tests/`, `tools/` | Unit tests and integration checks |
| `packaging/` | Build scripts (see [GUIDELINE.md](GUIDELINE.md)) |

Video playback and the RTSP console run in separate worker processes, so a stalled stream never freezes the UI. Passwords reach those processes only through standard input.

Code style: `PascalCase` for modules and classes, `camelCase` for functions. Keep camera I/O off the GUI thread. Put all styling in `gui/Appearance.py`. `main.ui` is generated, so edit `tools/BuildUi.py` instead.

## Checks

```powershell
.\venv\Scripts\python.exe -m pytest
.\venv\Scripts\python.exe -m ruff check .
.\venv\Scripts\python.exe -m ruff format .
```

The `tools\Check*.py` scripts are integration checks and need no camera. CI runs all of the above on every push.

## Data locations

- Error log: `%LOCALAPPDATA%\IPVidex\logs\errors.log`
- TLS certificates: `%LOCALAPPDATA%\IPVidex\tls\`
- Settings: `HKCU\Software\IPVidex`

## Third-party components

| Component | License |
|---|---|
| Qt 6 / PyQt6 | LGPL v3 / GPL v3 |
| libVLC / python-vlc | LGPL v2.1+ |
| MediaMTX 1.21.3 | MIT |
| cryptography | Apache 2.0 / BSD |

# Build Guide

How to build the Windows release of IPVidex.

## Prerequisites

- Windows 10 / 11, 64-bit
- Python 3.10+ (64-bit)
- VLC 3.x, 64-bit, in `C:\Program Files\VideoLAN\VLC`
- Inno Setup 6 (installer only)

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Before a release

Set the same version in `core\Version.py`, `AppVersion` in `packaging\Installer.iss`, the README badge and `CHANGELOG.md`. Then make sure the checks pass:

```powershell
.\venv\Scripts\python.exe -m pytest
.\venv\Scripts\python.exe -m ruff check .
```

## Build

| Artifact | Command | Output |
|---|---|---|
| Single executable | `.\packaging\Build.ps1` | `dist\IPVidex.exe` |
| Portable folder | `.\packaging\Build.ps1 -Mode onedir` | `dist\IPVidex\` |
| Installer | build the portable folder, then `& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\Installer.iss` | `dist\IPVidex-Setup.exe` |

Every build also writes `README.txt` and `LICENSE.txt` next to the executable. Both modes share `dist\`, so build the one you ship last.

Zip the portable folder as a whole, because `IPVidex.exe` needs its `_internal` folder:

```powershell
Compress-Archive -Path dist\IPVidex -DestinationPath dist\IPVidex-portable.zip -Force
```

## Verify

```powershell
dist\IPVidex\IPVidex.exe --check-runtime | Out-String                       # "available": true
Start-Process dist\IPVidex\IPVidex.exe -ArgumentList --self-test -Wait      # exits with 0
```

Then, on a clean machine: discover and log in to a camera, play live video, and start the RTMP server. Close the app and confirm that no `IPVidex.exe` or `mediamtx.exe` process is left running.

## Code signing

Builds are unsigned, so SmartScreen warns on first run (*More info → Run anyway*). To sign a release, sign every `.exe`, `.dll` and `.pyd` in `dist\IPVidex\` with `signtool`, build the installer, then sign `IPVidex-Setup.exe`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Set IPVIDEX_VLC_DIR ...` | Install 64-bit VLC 3.x, or pass `-VlcDirectory "D:\Path\To\VLC"`. |
| `running scripts is disabled` | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| `PyInstaller build failed` | Reinstall `requirements-dev.txt`, then delete `dist` and `build` and rebuild. |
| Missing DLLs in the portable copy | Ship the whole `IPVidex` folder, not just the `.exe`. |

# IPVidex — Build and Deployment Guide

This guide explains how to produce and ship the Windows release artifacts of IPVidex. For an overview of the application itself, see [README.md](README.md).

---

## Contents

1. [Release artifacts](#1-release-artifacts)
2. [Build machine prerequisites](#2-build-machine-prerequisites)
3. [One-time setup](#3-one-time-setup)
4. [Pre-release checklist](#4-pre-release-checklist)
5. [Build the portable folder](#5-build-the-portable-folder-onedir)
6. [Build the single executable](#6-build-the-single-executable-onefile)
7. [Build the installer](#7-build-the-installer)
8. [Verify a build](#8-verify-a-build)
9. [Distribute](#9-distribute)
10. [Code signing](#10-code-signing)
11. [Build configuration reference](#11-build-configuration-reference)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Release artifacts

| Artifact | Output | Size | Best for |
|---|---|---|---|
| **Installer** | `dist\IPVidex-Setup.exe` | LZMA2-compressed portable folder | Normal delivery. Installs to Program Files, adds Start-menu and optional desktop shortcuts, registers an uninstaller in *Apps & features*. |
| **Single executable** | `dist\IPVidex.exe` | ≈ 115 MB | Sending one file. No installation; unpacks its runtime to `%TEMP%` at every start, so it starts a few seconds slower. |
| **Portable folder** | `dist\IPVidex\` | ≈ 265 MB | USB sticks and machines where nothing may be installed. Fast start; the whole folder must be kept together. |

All three bundle Python, Qt, libVLC and MediaMTX. End users do not need to install anything else.

## 2. Build machine prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Windows | 10 / 11, 64-bit | |
| Python | 3.10 or later, **64-bit** | Released builds were produced with Python 3.14. |
| VLC desktop | 3.x, **64-bit** | Default location `C:\Program Files\VideoLAN\VLC`. Its `libvlc` and plugins are copied into the build. |
| Inno Setup | 6.x | Only for the installer. https://jrsoftware.org/isdl.php |
| Git | any | To check out the repository. |

`vendor\mediamtx\mediamtx.exe` is part of the repository and must be present.

## 3. One-time setup

Open **Windows PowerShell** in the repository root:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` installs the runtime dependencies plus PyInstaller, Ruff, pytest, PyAV and NumPy. The build script always uses `venv\Scripts\python.exe`.

If PowerShell refuses to run scripts, allow them for the current session only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## 4. Pre-release checklist

1. **Version**: set the same version (for example `1.0.1`) in `core\Version.py` (shown at the bottom right of the Discovery tab and embedded in the executable's file properties), `AppVersion` in `packaging\Installer.iss`, the version badge in `README.md` and a new entry in `CHANGELOG.md`.
2. **UI** — if `tools\BuildUi.py` changed, regenerate the form: `.\venv\Scripts\python.exe tools\BuildUi.py`.
3. **Quality gates** — all must pass:
   ```powershell
   .\venv\Scripts\python.exe -m pytest
   .\venv\Scripts\python.exe -m ruff check .
   .\venv\Scripts\python.exe tools\CheckRtspCommands.py
   .\venv\Scripts\python.exe tools\CheckTlsRelay.py
   .\venv\Scripts\python.exe tools\CheckLifecycle.py
   .\venv\Scripts\python.exe tools\CheckDiscovery.py
   .\venv\Scripts\python.exe tools\CheckRtmpServer.py
   .\venv\Scripts\python.exe tools\CheckVlc.py
   ```
4. **Clean tree** — commit or stash local changes so the build matches a known revision.

## 5. Build the portable folder (onedir)

```powershell
.\packaging\Build.ps1 -Mode onedir
```

Output:

```
dist\
├── IPVidex\
│   ├── IPVidex.exe
│   ├── README.txt          end-user notes (from packaging\CUSTOMER-README.txt)
│   ├── LICENSE.txt         GPL-3.0 license text (from LICENSE)
│   └── _internal\          Python, Qt, libVLC, MediaMTX, assets
└── build-packages.txt      exact Python package versions used
```

To ship it, compress the **entire** folder:

```powershell
Compress-Archive -Path dist\IPVidex -DestinationPath dist\IPVidex-portable.zip -Force
```

`IPVidex.exe` does not run without its `_internal` folder.

## 6. Build the single executable (onefile)

```powershell
.\packaging\Build.ps1            # onefile is the default mode
```

Output: `dist\IPVidex.exe`, `dist\README.txt` and `dist\LICENSE.txt`.

At every start the executable unpacks its runtime (about 260 MB) to a temporary folder under `%TEMP%`; worker processes reuse that folder. Allow for a few seconds of start-up time, longer on slow disks.

> Building onefile and onedir share the `dist\` folder. Build the mode you are about to ship last, or copy the artifacts away between builds.

## 7. Build the installer

The installer packages the portable folder, so build that first:

```powershell
.\packaging\Build.ps1 -Mode onedir
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\Installer.iss
```

Output: `dist\IPVidex-Setup.exe`.

Installer behaviour (`packaging\Installer.iss`):

| Setting | Default | How to change |
|---|---|---|
| Install location | `C:\Program Files\IPVidex` (administrator rights) | For a per-user install without UAC, set `PrivilegesRequired=lowest` and `DefaultDirName={localappdata}\IPVidex`. |
| Shortcuts | Start menu; desktop shortcut offered as an option | `[Icons]` and `[Tasks]` sections |
| Uninstall | Listed in *Apps & features* | Removes program files only; user data stays (see *Data locations* in [DEVELOPMENT.md](DEVELOPMENT.md#data-locations)). |
| Version / publisher | `AppVersion`, `AppPublisher` defines | Top of the script |

## 8. Verify a build

Run these checks on the built artifact, not on the source tree.

| Check | Command | Expected |
|---|---|---|
| Player runtime is bundled | `dist\IPVidex\IPVidex.exe --check-runtime \| Out-String` | `{"vlc": "3.0.x ...", "available": true}` |
| Application starts and closes cleanly | `Start-Process dist\IPVidex\IPVidex.exe -ArgumentList --self-test -Wait` | Window appears briefly and exits with code 0 |

Then complete a manual smoke test, ideally on a clean Windows machine without Python or VLC installed:

- [ ] The application starts and the taskbar shows the IPVidex icon.
- [ ] Discovery finds a camera; logging in opens its workspace; Overview loads.
- [ ] Live video plays; the Video and Image pages show the stream next to their settings.
- [ ] RTSP(S) tab: a stream plays; the RTSP command console returns responses.
- [ ] RTMP tab: the server starts, a camera can publish, statistics update, Stop releases the port.
- [ ] Closing the window ends every `IPVidex.exe` and `mediamtx.exe` process (check Task Manager).
- [ ] Installer only: uninstalling removes the program and its shortcuts.

## 9. Distribute

| Shipping | Send |
|---|---|
| Installer | `IPVidex-Setup.exe` |
| Single executable | `IPVidex.exe`, `README.txt` and `LICENSE.txt` |
| Portable folder | `IPVidex-portable.zip` |

Publish a SHA-256 checksum next to each download so users can verify their copy:

```powershell
Get-FileHash dist\IPVidex-Setup.exe -Algorithm SHA256
```

## 10. Code signing

The build is **not code-signed** by default. Consequences for end users:

- **SmartScreen** shows "Windows protected your PC"; the user can continue with *More info → Run anyway*.
- **Smart App Control** (Windows 11) blocks unsigned applications with no override.
- Antivirus products may flag the self-extracting single executable more often than the installer.

To sign, obtain a code-signing certificate that chains to the Microsoft Trusted Root Program. Options include a commercial OV certificate, Azure Artifact Signing, or SignPath Foundation's free certificates for qualifying open-source projects. Then:

1. Build the portable folder.
2. Sign every unsigned `.exe`, `.dll` and `.pyd` inside `dist\IPVidex\`, including `IPVidex.exe` and `_internal\vendor\mediamtx\mediamtx.exe`:
   ```powershell
   Get-ChildItem dist\IPVidex -Recurse -Include *.exe,*.dll,*.pyd |
     Where-Object { (Get-AuthenticodeSignature $_.FullName).Status -ne 'Valid' } |
     ForEach-Object { signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a $_.FullName }
   ```
3. Build the installer from the signed folder, then sign `dist\IPVidex-Setup.exe` the same way.

Prefer the installer or the portable folder for signed releases. The single executable unpacks its components at run time, so each of them would have to be signed before PyInstaller bundles them.

## 11. Build configuration reference

| File | Purpose |
|---|---|
| `packaging\Build.ps1` | Runs PyInstaller with the spec, writes `dist\build-packages.txt`, copies the end-user readme. Parameters: `-Mode onefile\|onedir`, `-VlcDirectory <path>`. |
| `packaging\IPVidex.spec` | PyInstaller specification: entry point `main.py`, bundled data (`main.ui`, `assets`, MediaMTX, libVLC), hidden imports for the worker modules. |
| `packaging\Installer.iss` | Inno Setup script for `IPVidex-Setup.exe`. |
| `packaging\CUSTOMER-README.txt` | End-user notes shipped as `README.txt`. |
| `LICENSE` | GPL-3.0 text shipped as `LICENSE.txt`. GPL-3.0 requires it to accompany every binary release. |

Environment variables read by the spec (set by `Build.ps1`):

| Variable | Default | Meaning |
|---|---|---|
| `IPVIDEX_VLC_DIR` | `C:\Program Files\VideoLAN\VLC` | VLC installation to copy `libvlc` and plugins from |
| `IPVIDEX_BUILD_MODE` | `onefile` | `onefile` or `onedir` |

What the spec deliberately leaves out to keep the build small: PyAV, OpenCV, NumPy, Tkinter, test frameworks, unused Qt modules (QML, Quick, WebEngine, Multimedia), and VLC plugin groups the player never uses (GUI, Lua, visualisations, stream output, muxers, service discovery, control interfaces).

The single executable is also the worker: the GUI relaunches it with `infrastructure.VlcProcess` or `infrastructure.RtspCommands` as the first argument. Keep both modules listed in `hiddenimports`.

## 12. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Set IPVIDEX_VLC_DIR to a VLC 3.x x64 installation directory` | VLC was not found. Install 64-bit VLC 3.x or pass `-VlcDirectory "D:\Path\To\VLC"`. |
| `running scripts is disabled on this system` | Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` and build again. |
| `The term '...ISCC.exe' is not recognized` | Inno Setup 6 is not installed or lives elsewhere; adjust the path. |
| `PyInstaller build failed` | Run `.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt`, then rebuild. A clean rebuild: `Remove-Item dist, build -Recurse -Force`. |
| Video shows `VLC_NOT_INSTALLED` in a packaged build | The build machine's VLC was 32-bit or incomplete. Reinstall 64-bit VLC and rebuild. |
| The portable copy reports missing DLLs | Only `IPVidex.exe` was copied. Ship the whole `IPVidex` folder. |
| Users report "Windows protected your PC" | Expected for unsigned builds; see [Code signing](#10-code-signing). |

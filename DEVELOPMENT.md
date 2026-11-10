# IPVidex — Developer Guide

How to run IPVidex from source, how it is structured, and how changes are checked. For building release artifacts, see [GUIDELINE.md](GUIDELINE.md).

---

## Contents

1. [Run from source](#run-from-source)
2. [Architecture](#architecture)
3. [Source layout](#source-layout)
4. [Conventions](#conventions)
5. [Quality checks](#quality-checks)
6. [Data locations](#data-locations)
7. [Known limitations](#known-limitations)
8. [Third-party components](#third-party-components)
9. [Releasing](#releasing)

---

## Run from source

Requirements: Windows 10 / 11 64-bit, Python 3.10 or later (64-bit), and **VLC desktop 3.x, 64-bit** in its default location (https://www.videolan.org/vlc/).

```powershell
git clone <repository-url> IPVidex
cd IPVidex
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv\Scripts\python.exe main.py
```

Check that the player runtime is found:

```powershell
.\venv\Scripts\python.exe worker.py --check-runtime
```

## Architecture

IPVidex runs as one GUI process plus short-lived child processes, so a crash or stall in a codec or in the network never blocks the interface:

| Process | Started by | Purpose |
|---|---|---|
| `IPVidex.exe` (GUI) | user | Qt interface; ONVIF calls run on worker threads |
| `IPVidex.exe infrastructure.VlcProcess` | each video view | libVLC playback into the GUI window, statistics over stdout |
| `IPVidex.exe infrastructure.RtspCommands` | RTSP console | independent RTSP test session |
| `mediamtx.exe` | RTMP / P2P tab | ingest server with a generated temporary configuration |

Credentials reach worker processes only through their standard input.

## Source layout

| Path | Responsibility |
|---|---|
| `main.py`, `worker.py` | Entry points; the same executable serves as GUI and worker |
| `core/` | `Models` (connection settings), `Paths`, `Runtime` (worker commands), `Diagnostics` (error log), `Version` |
| `infrastructure/` | Network transport and certificate pinning, HTTP parsing, Digest authentication, ONVIF SOAP and WS-Discovery, RTSP parsing, TLS relay, worker processes, MediaMTX configuration, self-signed certificates |
| `services/OnvifDevice.py` | ONVIF device operations (read and write) |
| `gui/` | Main window, discovery hub, device workspace, RTSP tab and console, ingest-server tabs, theme |
| `gui/pages/` | One module per device page, shared form helpers and the preview panel |
| `assets/` | Application and toolbar icons |
| `vendor/mediamtx/` | MediaMTX runtime and its license |
| `packaging/` | PyInstaller spec, build script, Inno Setup script, end-user readme |
| `docs/images/` | Screenshots used by the README |
| `tests/` | Unit tests (pytest) |
| `tools/` | `BuildUi.py` (generates `main.ui`) and `Check*.py` integration checks |

## Conventions

- Modules and classes `PascalCase`, functions and variables `camelCase`, constants `UPPER_SNAKE_CASE`.
- No blocking camera I/O on the GUI thread; device calls go through `DeviceWorkspace.runTask`.
- `main.ui` is generated: edit `tools/BuildUi.py`, then run `python tools/BuildUi.py`.
- All styling lives in `gui/Appearance.py`.

## Quality checks

```powershell
.\venv\Scripts\python.exe -m pytest                       # unit tests
.\venv\Scripts\python.exe -m ruff check .                 # lint
.\venv\Scripts\python.exe -m ruff format .                # format
```

Integration checks (none of them contact a real camera):

| Script | Verifies | Needs a display |
|---|---|---|
| `tools\CheckRtspCommands.py` | RTSP Digest authentication, framing, CSeq and session lifecycle | no |
| `tools\CheckTlsRelay.py` | RTSPS relay rewriting, fragmentation, interleaved media | no |
| `tools\CheckLifecycle.py` | Worker-thread lifecycle and stale-result handling | no |
| `tools\CheckDiscovery.py` | Concurrent device logins, tabs and shutdown | no |
| `tools\CheckRtmpServer.py` | RTMP publish/read through MediaMTX and port cleanup | no |
| `tools\CheckVlc.py` | Native video and audio playback | yes |
| `tools\CheckLatency.py --variants` | Player delay behind real time | yes |

`CheckRtmpServer`, `CheckVlc` and `CheckLatency` generate test streams with PyAV and NumPy from `requirements-dev.txt`.

GitHub Actions (`.github/workflows/ci.yml`) runs lint, format check, unit tests and the display-free integration checks on Windows with Python 3.10 and 3.14 for every push to `main` and every pull request.

## Data locations

| Item | Installed / packaged build | Source checkout |
|---|---|---|
| Error log | `%LOCALAPPDATA%\IPVidex\logs\errors.log` | `logs\errors.log` |
| Ingest-server TLS certificates | `%LOCALAPPDATA%\IPVidex\tls\` | `tls\` |
| Remembered form fields | `HKEY_CURRENT_USER\Software\IPVidex\IPVidex` | same |

The uninstaller removes the program files only; delete the folders and registry key above to remove all user data.

## Known limitations

- **Unsigned binaries.** Windows SmartScreen warns on first run, and Smart App Control blocks unsigned applications. See *Code signing* in [GUIDELINE.md](GUIDELINE.md).
- **Player latency.** libVLC keeps roughly 330–380 ms behind real time even on a perfect network (measured with `tools\CheckLatency.py`).
- **Discovery is IPv4 only**, and multicast must reach the camera's network segment.
- **One stream at a time.** Only one video view plays at once; high-resolution H.265 on machines without H.265 hardware decoding may exceed what an older CPU can decode in real time.
- The ingest servers accept unauthenticated publish/read on the configured path and do not record or transcode; use them on trusted networks.

## Third-party components

| Component | License | Use |
|---|---|---|
| Python | PSF License | Runtime |
| Qt 6 | LGPL v3 | User interface |
| PyQt6 | GPL v3 or Riverbank commercial license | Qt bindings |
| libVLC / VLC plugins | LGPL v2.1+ (some plugins GPL v2+) | Video playback |
| python-vlc | LGPL v2.1+ | libVLC bindings |
| MediaMTX 1.21.3 | MIT (`vendor/mediamtx/LICENSE`) | Ingest servers |
| cryptography | Apache 2.0 or BSD | Self-signed certificates |

## Releasing

1. Set the same version in `core\Version.py` (also embedded in the executable's file properties), `AppVersion` in `packaging\Installer.iss`, the version badge at the top of [README.md](README.md), and a new entry in [CHANGELOG.md](CHANGELOG.md).
2. Build, verify and distribute as described in [GUIDELINE.md](GUIDELINE.md).
3. Tag the release commit: `git tag -a vX.Y.Z -m "IPVidex X.Y.Z"`.

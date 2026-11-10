# -*- mode: python ; coding: utf-8 -*-
"""Portable Windows x64 build. Deliberately excludes test data and legacy decoders."""
from pathlib import Path
import os
import sys
from PyInstaller.utils.hooks import copy_metadata
root = Path(SPECPATH).parent
vlc = Path(os.environ.get('IPVIDEX_VLC_DIR', r'C:\Program Files\VideoLAN\VLC'))
if not (vlc/'libvlc.dll').is_file():
    raise RuntimeError('Set IPVIDEX_VLC_DIR to a VLC 3.x x64 installation directory.')
skip = {'gui','lua','visualization','access_output','stream_out','mux','services_discovery','control','video_splitter'}
vlcFiles = [(str(vlc/name), 'vendor/vlc') for name in ('libvlc.dll','libvlccore.dll','COPYING.txt','AUTHORS.txt') if (vlc/name).is_file()]
for path in (vlc/'plugins').rglob('*'):
    relative = path.relative_to(vlc)
    if path.is_file() and relative.parts[1] not in skip and path.suffix.lower() == '.dll':
        vlcFiles.append((str(path), str(Path('vendor/vlc')/relative.parent)))
datas = [(str(root/'main.ui'),'.'), (str(root/'assets'),'assets'),
         (str(root/'vendor/mediamtx/mediamtx.exe'),'vendor/mediamtx'),
         (str(root/'vendor/mediamtx/LICENSE'),'vendor/mediamtx')] + vlcFiles
for package in ('PyQt6','PyQt6-Qt6','PyQt6_sip','python-vlc'):
    datas += copy_metadata(package)
pythonLicense = Path(sys.base_prefix)/'LICENSE.txt'
if pythonLicense.is_file():
    datas.append((str(pythonLicense),'licenses/Python'))
# Single executable: main.py is the only entry point and dispatches to the media
# worker (infrastructure.VlcProcess / infrastructure.RtspCommands) when relaunched
# with a worker argument, so one onefile exe covers both the GUI and the workers.
analysis = Analysis([str(root/'main.py')], pathex=[str(root)],
                    binaries=[], datas=datas,
                    hiddenimports=['PyQt6.QtSvg','vlc','worker','infrastructure.VlcProcess','infrastructure.RtspCommands'],
                    excludes=['av','cv2','numpy','tkinter','unittest','pytest','PyQt6.QtQml','PyQt6.QtQuick','PyQt6.QtWebEngineCore','PyQt6.QtMultimedia'],
                    hookspath=[], runtime_hooks=[], noarchive=False)
pyz = PYZ(analysis.pure)
# Build mode is selected by Build.ps1 via IPVIDEX_BUILD_MODE (default: onefile).
# console=False keeps the media worker windowless; its stdin/stdout stay wired
# through the QProcess pipes the GUI connects.
appIcon = str(root / 'assets' / 'IPVidex.ico')
# Windows version resource (Properties > Details), from the single version source core/Version.py.
from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)
version = {}
exec((root / 'core' / 'Version.py').read_text(encoding='utf-8'), version)
version = version['VERSION']
numbers = tuple(int(part) for part in version.split('.')) + (0,)
versionInfo = VSVersionInfo(
    ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
    kids=[StringFileInfo([StringTable('040904B0', [
              StringStruct('CompanyName', 'Vivoo'),
              StringStruct('FileDescription', 'IPVidex - IP Video Protocol Utility'),
              StringStruct('LegalCopyright', 'Copyright (C) 2026 Vivoo. GPL-3.0.'),
              StringStruct('FileVersion', version),
              StringStruct('InternalName', 'IPVidex'),
              StringStruct('OriginalFilename', 'IPVidex.exe'),
              StringStruct('ProductName', 'IPVidex'),
              StringStruct('ProductVersion', version)])]),
          VarFileInfo([VarStruct('Translation', [0x0409, 1200])])])
mode = os.environ.get('IPVIDEX_BUILD_MODE', 'onefile').lower()
if mode == 'onedir':
    # Portable folder: the EXE carries only the bootloader; COLLECT lays the
    # binaries + datas beside it under dist/IPVidex. Faster startup, many files.
    exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True,
              name='IPVidex', debug=False, bootloader_ignore_signals=False,
              strip=False, upx=False, console=False, icon=appIcon, version=versionInfo)
    release = COLLECT(exe, analysis.binaries, analysis.datas,
                      strip=False, upx=False, name='IPVidex')
else:
    # One file: pack binaries + datas into the EXE itself (no COLLECT).
    exe = EXE(pyz, analysis.scripts, analysis.binaries, analysis.datas, [],
              name='IPVidex', debug=False, bootloader_ignore_signals=False,
              strip=False, upx=False, runtime_tmpdir=None, console=False, icon=appIcon, version=versionInfo)

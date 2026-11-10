"""Launch allowlisted worker modules in source and portable builds."""

import os
import sys

WORKER_MODULES = ("infrastructure.VlcProcess", "infrastructure.RtspCommands")
CHECK_RUNTIME = "--check-runtime"


def workerCommand(module):
    if module not in WORKER_MODULES:
        raise ValueError("Unknown worker module")
    if getattr(sys, "frozen", False):
        # Single-file build: relaunch this same executable as the worker. QProcess
        # inherits our environment, so PyInstaller's onefile runtime reuses the
        # already-unpacked directory instead of extracting the archive on every spawn.
        return sys.executable, [module]
    return sys.executable, ["-m", module]


def detachWorker(process):
    """Disconnect the GUI handlers from a worker QProcess. A bare disconnect() would also cut Qt's internal destroyed signal and warn."""
    for signal in (process.started, process.readyReadStandardOutput, process.readyReadStandardError, process.finished, process.errorOccurred):
        signal.disconnect()


def configureVlc():
    from core.Paths import ROOT

    folder = ROOT / "vendor" / "vlc"
    if not (folder / "libvlc.dll").is_file():
        return
    os.environ["PYTHON_VLC_LIB_PATH"] = str(folder / "libvlc.dll")
    os.environ["PYTHON_VLC_MODULE_PATH"] = str(folder / "plugins")
    os.environ["VLC_PLUGIN_PATH"] = str(folder / "plugins")
    os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        # Keep the directory cookie alive for the duration of the process.
        global _vlcDirectory
        _vlcDirectory = os.add_dll_directory(str(folder))

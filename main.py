"""Desktop entry point; the same executable also serves the media worker.

In the single-file (onefile) build there is only one IPVidex.exe. When the GUI
needs an isolated VLC / RTSP subprocess it relaunches this same executable with
the worker module as the first argument; PyInstaller reuses the parent's already
unpacked runtime, so no re-extraction happens on each spawn.
"""

import sys
from core.Runtime import CHECK_RUNTIME, WORKER_MODULES

SELF_TEST_CLOSE_MS = 500
APP_USER_MODEL_ID = "Vivoo.IPVidex"


def useOwnTaskbarIdentity():
    """Windows groups taskbar buttons by process identity; without its own ID a source run
    is shown as python.exe with the Python icon instead of the IPVidex window icon."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)


def runGui():
    from PyQt6.QtCore import QTimer
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import QApplication
    from core.Diagnostics import installExceptionHandler
    from gui.MainController import MainWindow

    installExceptionHandler()
    useOwnTaskbarIdentity()
    app = QApplication(sys.argv)
    app.setFont(QFont("Tahoma", 9))
    window = MainWindow()
    window.show()
    if "--self-test" in sys.argv:
        QTimer.singleShot(SELF_TEST_CLOSE_MS, window.close)
    return app.exec()


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] in (*WORKER_MODULES, CHECK_RUNTIME):
        from worker import main as workerMain

        sys.exit(workerMain())
    sys.exit(runGui())

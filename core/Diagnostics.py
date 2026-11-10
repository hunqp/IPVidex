"""Keep unhandled UI errors from causing silent process termination, and show them clearly."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import platform
import re
import sys
import traceback
from core.Paths import DATA_ROOT
from core.Version import VERSION

# user:password@ inside any URL (rtsp://, http://, ...).
URL_CREDENTIALS = re.compile(r"(?<=://)[^/@\s]+@")
SUMMARY_LIMIT = 300
showing = False


def masked(text):
    return URL_CREDENTIALS.sub("***@", text)


def logFile():
    return DATA_ROOT / "logs" / "errors.log"


def writeLog(kind, tb):
    # Do not log exception messages or locals: library errors can embed
    # URLs with device credentials. Stack frames and type identify code.
    try:
        logFile().parent.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger("ipvidex.errors")
        if not logger.handlers:
            logger.addHandler(RotatingFileHandler(logFile(), maxBytes=1024 * 1024, backupCount=2, encoding="utf-8"))
        logger.error("%s\n%s", kind.__name__, "".join(traceback.format_tb(tb)))
    except OSError:
        pass


def errorReport(kind, value, tb):
    """(summary, location, details) for the user; URL credentials are masked."""
    message = masked(str(value)).strip()
    summary = f"{kind.__name__}: {message}" if message else kind.__name__
    if len(summary) > SUMMARY_LIMIT:
        summary = summary[:SUMMARY_LIMIT] + "…"
    frames = traceback.extract_tb(tb)
    location = f"{Path(frames[-1].filename).name}, line {frames[-1].lineno}, in {frames[-1].name}" if frames else "unknown"
    from PyQt6.QtCore import QT_VERSION_STR

    header = f"IPVidex {VERSION} · Python {platform.python_version()} · Qt {QT_VERSION_STR} · {platform.platform()}"
    details = f"{header}\nLog: {logFile()}\n\n" + masked("".join(traceback.format_exception(kind, value, tb)))
    return summary, location, details


def showError(kind, value, tb):
    global showing
    from PyQt6.QtWidgets import QApplication, QMessageBox

    if QApplication.instance() is None or showing:
        return
    summary, location, details = errorReport(kind, value, tb)
    box = QMessageBox(QMessageBox.Icon.Critical, "IPVidex — Unexpected error", summary)
    box.setInformativeText(f"Location: {location}\n\nThe action did not complete. IPVidex keeps running; reopen the affected page if it looks wrong.")
    box.setDetailedText(details)
    copy = box.addButton("Copy details", QMessageBox.ButtonRole.ActionRole)
    box.addButton(QMessageBox.StandardButton.Close)
    showing = True
    try:
        box.exec()
    finally:
        showing = False
    if box.clickedButton() is copy:
        QApplication.clipboard().setText(details)


def installExceptionHandler():
    def handle(kind, value, tb):
        writeLog(kind, tb)
        showError(kind, value, tb)

    sys.excepthook = handle

import sys

from core.Diagnostics import errorReport, masked


def raised(error):
    try:
        raise error
    except Exception:
        return sys.exc_info()


def testUrlCredentialsAreMasked():
    assert masked("rtsp://admin:secret@192.0.2.1:554/live failed") == "rtsp://***@192.0.2.1:554/live failed"
    assert masked("no url here") == "no url here"


def testReportShowsTypeMessageAndLocation():
    summary, location, details = errorReport(*raised(ValueError("cannot open rtsp://admin:secret@192.0.2.1/live")))
    assert summary == "ValueError: cannot open rtsp://***@192.0.2.1/live"
    assert location.startswith("TestDiagnostics.py, line ") and location.endswith("in raised")
    assert "secret" not in details and "Traceback" in details and "IPVidex " in details


def testReportWithoutMessageShowsType():
    summary, _, _ = errorReport(*raised(RuntimeError()))
    assert summary == "RuntimeError"

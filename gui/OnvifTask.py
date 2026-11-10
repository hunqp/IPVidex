"""Run one blocking device call off the GUI thread."""

from PyQt6.QtCore import QThread, pyqtSignal
from infrastructure.Onvif import OnvifFault


def faultMessage(fault):
    return fault.reason or f"HTTP {fault.status} {fault.subcode}".strip()


class OnvifTask(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            self.succeeded.emit(self.function())
        except OnvifFault as fault:
            self.failed.emit(faultMessage(fault))
        except Exception as exc:
            self.failed.emit(str(exc) or type(exc).__name__)

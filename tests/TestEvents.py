import threading
from core.Models import Config
from gui.pages.EventsPage import EventWorker
from infrastructure.Network import Transport
from infrastructure.Onvif import OnvifSession
from services.OnvifDevice import OnvifDevice


def testStoppedWorkerReleasesItsSubscription(monkeypatch):
    """Regression: unsubscribe ran on the cancelled transport and never reached the device."""
    polling, released = threading.Event(), []

    def pull(session, pull, timeout):
        polling.set()
        session.transport.stop.wait(5)
        session.transport.checkpoint()

    def unsubscribe(session, pull):
        released.append((pull, session.transport.stop.is_set()))

    monkeypatch.setattr(OnvifSession, "createPullPoint", lambda session, termination: "subscription")
    monkeypatch.setattr(OnvifSession, "pullMessages", pull)
    monkeypatch.setattr(OnvifSession, "unsubscribe", unsubscribe)
    config = Config("127.0.0.1")
    worker = EventWorker(OnvifDevice(OnvifSession(config, Transport(config, threading.Event()))))
    thread = threading.Thread(target=worker.run)
    thread.start()
    assert polling.wait(5)
    worker.stop()
    thread.join(5)
    assert released == [("subscription", False)]

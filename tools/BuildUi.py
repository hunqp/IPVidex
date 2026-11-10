"""Generate IPVidex's Qt Designer-compatible main.ui; application logic and texts live in gui/."""

import sys
import xml.etree.ElementTree as E
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from gui.Appearance import STYLE  # noqa: E402  (needs ROOT on sys.path)

TITLE = "IPVidex"

ui = E.Element("ui", version="4.0")
E.SubElement(ui, "class").text = "MainWindow"
w = E.SubElement(ui, "widget", {"class": "QMainWindow", "name": "MainWindow"})


def prop(o, n, t, v):
    p = E.SubElement(o, "property", name=n)
    E.SubElement(p, t).text = str(v)


def box(parent, cls, name):
    return E.SubElement(parent, "layout", {"class": cls, "name": name})


def row(parent, name):
    return box(E.SubElement(parent, "item"), "QHBoxLayout", name)


def widget(parent, cls, name, text=None, **pos):
    item = E.SubElement(parent, "item", {k: str(v) for k, v in pos.items()})
    o = E.SubElement(item, "widget", {"class": cls, "name": name})
    if text is not None:
        prop(o, "text", "string", text)
    return o


def field(grid, r, c, label, name, cls="QLineEdit"):
    widget(grid, "QLabel", name + "Label", label, row=r, column=c)
    return widget(grid, cls, name, row=r, column=c + 1)


def size(o, n, width, height):
    p = E.SubElement(o, "property", name=n)
    s = E.SubElement(p, "size")
    E.SubElement(s, "width").text = str(width)
    E.SubElement(s, "height").text = str(height)


def combo(o, values):
    for value in values:
        p = E.SubElement(o, "item")
        prop(p, "text", "string", value)


def spin(o, minimum, maximum, value, double=False):
    for n, v in [("minimum", minimum), ("maximum", maximum), ("value", value)]:
        prop(o, n, "double" if double else "number", v)


p = E.SubElement(w, "property", name="geometry")
r = E.SubElement(p, "rect")
for n, v in [("x", 0), ("y", 0), ("width", 1120), ("height", 760)]:
    E.SubElement(r, n).text = str(v)
prop(w, "windowTitle", "string", TITLE)
prop(w, "styleSheet", "string", STYLE)
fontProperty = E.SubElement(w, "property", name="font")
font = E.SubElement(fontProperty, "font")
E.SubElement(font, "family").text = "Tahoma"
E.SubElement(font, "pointsize").text = "9"
center = E.SubElement(w, "widget", {"class": "QWidget", "name": "centralwidget"})
main = box(center, "QVBoxLayout", "mainLayout")

# Header: brand (added in code) and settings.
head = row(main, "headerLayout")
widget(head, "QPushButton", "settingsButton", "Settings")

# Settings dialog content (moved into a QDialog by the main window).
settings = E.SubElement(center, "widget", {"class": "QWidget", "name": "advancedContent"})
form = box(settings, "QGridLayout", "advancedGrid")
o = field(form, 0, 0, "Connection timeout (s)", "timeoutSpin", "QDoubleSpinBox")
spin(o, 0.2, 10, 2, True)
o = field(form, 1, 0, "ONVIF port", "onvifPortSpin", "QSpinBox")
spin(o, 1, 65535, 80)
o = field(form, 2, 0, "ONVIF device path", "onvifPathEdit")
prop(o, "placeholderText", "string", "Documented path only; e.g. /onvif/device_service")
widget(form, "QCheckBox", "onvifHttpsCheck", "ONVIF HTTPS", row=3, column=1)

tabs = widget(main, "QTabWidget", "tabs")


def tab(name, title):
    o = E.SubElement(tabs, "widget", {"class": "QWidget", "name": name})
    a = E.SubElement(o, "attribute", name="title")
    E.SubElement(a, "string").text = title
    return box(o, "QVBoxLayout", name + "Layout")


tab("discoveryTab", "Discovery")
viewer = tab("viewerTab", "RTSP(S)")
viewer.set("stretch", "0,0,0,0,1")
grid = box(E.SubElement(viewer, "item"), "QGridLayout", "viewerForm")
for r, label, name in [(0, "Main stream RTSP URL", "mainUrlEdit"), (1, "Minor stream RTSP URL", "subUrlEdit")]:
    o = field(grid, r, 0, label, name)
    prop(o, "placeholderText", "string", "rtsp://<IP_CAMERA>:554/path or rtsps://camera:322/path")
o = field(grid, 2, 0, "Stream to open", "streamCombo", "QComboBox")
combo(o, ["Main", "Minor"])
for r, label, name in ((3, "RTSP username (optional)", "rtspUsernameEdit"), (4, "RTSP password", "rtspPasswordEdit")):
    edit = field(grid, r, 0, label, name)
prop(edit, "echoMode", "enum", "QLineEdit::Password")
widget(grid, "QCheckBox", "rtspAutoTrustCheck", "Automatically fetch and trust camera certificate (RTSPS)", row=5, column=1)
widget(grid, "QLabel", "rtspCaEditLabel", "RTSPS certificate", row=6, column=0)
ca = box(E.SubElement(grid, "item", row="6", column="1"), "QHBoxLayout", "rtspCaRow")
o = widget(ca, "QLineEdit", "rtspCaEdit")
prop(o, "placeholderText", "string", "Only for rtsps:// — certificate (.pem) exported from this camera")
widget(ca, "QPushButton", "rtspCaButton", "Browse…")
a = row(viewer, "viewerActions")
for name, text in [("playButton", "Connect"), ("stopStreamButton", "Disconnect")]:
    widget(a, "QPushButton", name, text)
widget(viewer, "QLabel", "streamStatusLabel", "Disconnected")
widget(viewer, "QLabel", "metadataLabel", "")
video = widget(viewer, "QLabel", "videoLabel", "")
prop(video, "alignment", "set", "Qt::AlignCenter")
prop(video, "styleSheet", "string", "background:#202020;color:white;")
size(video, "minimumSize", 320, 160)
E.SubElement(ui, "resources")
E.SubElement(ui, "connections")
E.indent(ui)
E.ElementTree(ui).write(ROOT / "main.ui", encoding="UTF-8", xml_declaration=True)

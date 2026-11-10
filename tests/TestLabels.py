from gui.pages.ImagingPage import LABELS, label


def testImagingLabelsAreText():
    assert all(isinstance(text, str) for text in LABELS.values())


def testUnknownImagingPathFallsBackToPath():
    assert label("Focus/AutoFocusMode") == "Focus/AutoFocusMode"

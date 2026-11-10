"""Compact desktop theme and geometry; all application styling lives here."""

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import QAbstractSpinBox, QApplication
from core.Paths import ICONS

WINDOW_SIZE = (1120, 760)
MINIMUM_WINDOW_SIZE = (960, 640)

STYLE = """
QWidget { font-family:Tahoma;font-size:9pt;font-weight:400;color:#202833; }
QMainWindow,QDialog,QWidget#centralwidget { background:#F5F6F8; }
QLabel { background:transparent; }
QLabel#brandTitle { font-size:14pt;font-weight:800;color:#12325C; }
QLabel#brandSubtitle { font-size:8pt;color:#6A7686; }
QLabel#versionLabel { font-size:8pt;color:#6A7686; }
QPushButton#headerIcon { background:transparent;border:0;padding:0;min-height:0; }
QPushButton#headerIcon:hover { background:#DDEAF7; }
QToolTip { background:#FFFFFF;color:#202833;border:1px solid #C9CFD7;padding:3px 5px; }
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox { background:#FFFFFF;border:1px solid #C9CFD7;border-radius:4px;padding:2px 6px;min-height:17px;selection-background-color:#DCEAF8;selection-color:#202833; }
QLineEdit:hover,QComboBox:hover,QSpinBox:hover,QDoubleSpinBox:hover { border-color:#AEB7C2; }
QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus { border-color:#2474C7; }
QLineEdit:disabled,QComboBox:disabled,QSpinBox:disabled { background:#F2F3F5;color:#9AA3AE; }
QSpinBox[plain="true"]::up-button,QSpinBox[plain="true"]::down-button { subcontrol-origin:padding;width:0;border:0; }
QComboBox::drop-down { border:0;width:18px; }
QPushButton { background:#FFFFFF;border:1px solid #C9CFD7;border-radius:4px;padding:2px 10px;min-height:19px; }
QPushButton:hover { background:#EEF4FB;border-color:#9DBEE0; }
QPushButton:pressed { background:#DCEAF8;border-color:#2474C7; }
QPushButton:disabled { color:#A3ABB5;background:#F2F3F5;border-color:#DDE1E6; }
QGroupBox { border:1px solid #D5DAE1;border-radius:4px;margin-top:8px;padding-top:8px; }
QTabWidget::pane { background:#FFFFFF;border:1px solid #D5DAE1;top:-1px; }
QTabWidget::tab-bar { left:8px; }
QWidget#viewerTab { background:#FFFFFF; }
QTabBar::tab { background:#ECEEF1;color:#4A5563;border:1px solid #D5DAE1;border-bottom:0;border-top-left-radius:4px;border-top-right-radius:4px;padding:5px 14px;min-height:16px;margin-right:2px; }
QTabBar::tab:selected { background:#FFFFFF;color:#202833;border-top:2px solid #2474C7;padding-top:4px; }
QTabBar::tab:hover:!selected { background:#F5F7FA;color:#202833; }
QSplitter::handle { background:#FFFFFF; }
QTableWidget,QTextEdit,QPlainTextEdit { background:#FFFFFF;border:1px solid #D5DAE1;border-radius:4px;selection-background-color:#DCEAF8;selection-color:#14385E;outline:0; }
QCheckBox::indicator { width:15px;height:15px;margin-right:4px; }
QCheckBox::indicator:unchecked { border:1px solid #9AA4B0;border-radius:3px;background:#FFFFFF; }
QCheckBox::indicator:unchecked:hover { border-color:#2474C7; }
QCheckBox::indicator:checked { image:url("@ICONS@/checked.svg"); }
QCheckBox::indicator:indeterminate { image:url("@ICONS@/partial.svg"); }
QCheckBox::indicator:disabled { border-color:#D5DAE1;background:#F2F3F5; }
QTableWidget { gridline-color:#E6E9ED;alternate-background-color:#FAFBFC; }
QTableWidget::item { padding:2px 6px;font-size:9pt; }
QTableWidget::item:selected { background:#DCEAF8;color:#14385E; }
QHeaderView { background:#F3F5F7; }
QHeaderView::section { background:#F3F5F7;color:#202833;border:0;border-right:1px solid #E1E5EA;border-bottom:1px solid #D5DAE1;padding:4px 8px;font-weight:600; }
QWidget#discoveryTab { background:#FFFFFF; }
QTabBar#discoveryNav::tab { background:transparent;border:0;border-bottom:2px solid transparent;border-radius:0;margin:0 2px 0 0;padding:5px 10px;color:#4A5563; }
QTabBar#discoveryNav::tab:hover:!selected { background:#F0F3F6; }
QTabBar#discoveryNav::tab:selected { color:#202833;font-weight:600;border-bottom:2px solid #4A5563; }
QTabBar#discoveryNav::tab:disabled { color:#A3ABB5; }
QPushButton#discoveryIcon { padding:0;min-width:28px;max-width:28px;min-height:28px;max-height:28px; }
QPushButton#discoveryIcon:checked { background:#FCEFF0;border-color:#E3A4A9; }
QLabel#discoveryConnection { color:#4A5563; }
QFrame#discoveryPanel { background:#FFFFFF;border:1px solid #D5DAE1;border-radius:3px; }
QLabel#discoveryStatus { color:#4A5563;border:0;border-top:1px solid #E6E9ED;padding-top:3px; }
QLabel#discoveryFieldLabel { color:#4A5563; }
QFrame#discoveryPanel QTableWidget,QFrame#discoveryPanel QPlainTextEdit { border:0;border-radius:0;background:#FFFFFF; }
QFrame#discoveryPanel QTableWidget::item:selected { background:#DCEAF8;color:#14385E; }
QLabel#discoveryVideo { background:#1E2228;color:#8A939D;border-radius:2px; }
QLabel#discoveryChip { background:#F3F5F7;color:#66717C;border:1px solid #D5DAE1;border-radius:3px;padding:1px 5px;font-size:8pt;font-weight:400;font-style:normal; }
QPushButton#rtspCommandTag { background:#F4F8FD;color:#2467A8;border:1px solid #7BA9D8;border-radius:8px;padding:0 10px;min-height:26px;max-height:26px;font-weight:400; }
QLabel#rtspCommandProgress { color:#66717C;font-size:8pt; }
QGroupBox#rtspCommandPanel { margin-top:0;padding-top:0; }
QToolButton#rtspRequestOptions { background:#F3F5F7;color:#344454;border:1px solid #CCD5DF;border-radius:4px;padding:4px 8px; }
QToolButton#rtspRequestOptions:hover { background:#EAF0F6; }
QToolButton#rtspRequestOptions:checked { background:#EAF0F6;color:#344454;border-color:#B5C5D6; }
QPushButton#rtspCommandTag:hover { background:#EDF5FD;border-color:#347FC5; }
QPushButton#rtspCommandTag:pressed { background:#DCECFB;border-color:#2467A8; }
QPushButton#rtspCommandTag:disabled { color:#91A7BC;border-color:#C6D6E5;background:#F7F9FB; }
QLabel#discoveryUri { color:#66717C; }
QPushButton#discoveryCopy { padding:0;min-height:0; }
QLabel#discoverySection { color:#202833;font-weight:600;padding:4px 0 2px 0;border:0;border-bottom:1px solid #E1E5EA; }
QTableCornerButton::section { background:#F3F5F7;border:0;border-bottom:1px solid #D5DAE1; }
QScrollBar:vertical { background:transparent;width:10px;margin:2px; }
QScrollBar:horizontal { background:transparent;height:10px;margin:2px; }
QScrollBar::handle:vertical { background:#C5CBD3;border-radius:3px;min-height:28px; }
QScrollBar::handle:horizontal { background:#C5CBD3;border-radius:3px;min-width:28px; }
QScrollBar::handle:hover { background:#A7AFBA; }
QScrollBar::add-line,QScrollBar::sub-line { width:0;height:0; }
QScrollBar::add-page,QScrollBar::sub-page { background:transparent; }
QPushButton#playButton,QPushButton#discoveryPrimary { background:#FFFFFF;color:#0E63D8;border:1px solid #0E63D8;border-radius:4px;padding:3px 14px;font-weight:600; }
QPushButton#playButton:hover,QPushButton#discoveryPrimary:hover { background:#F0F6FE;color:#0A4FB0;border-color:#0A4FB0; }
QPushButton#playButton:pressed,QPushButton#discoveryPrimary:pressed { background:#E2EDFB; }
QPushButton#playButton:disabled,QPushButton#discoveryPrimary:disabled { background:#FFFFFF;color:#AEC6EC;border-color:#D4DFEE; }
""".replace("@ICONS@", ICONS.as_posix())


def plainSpinBox(box):
    """Hide the step buttons. With a stylesheet, Qt collapses a NoButtons edit field to 1 px unless the buttons are styled too."""
    box.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    box.setProperty("plain", True)
    box.lineEdit().setTextMargins(2, 0, 0, 0)
    return box


def applyTheme(window):
    """Compact geometry sized for Tahoma 9 pt at normal Windows scaling."""
    # Unhinted, antialiased glyphs: smoother glyphs with even letter spacing.
    font = QApplication.font()
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    QApplication.setFont(font)
    window.setStyleSheet(STYLE)
    window.resize(*WINDOW_SIZE)
    window.setMinimumSize(*MINIMUM_WINDOW_SIZE)
    window.mainLayout.setContentsMargins(0, 6, 0, 0)
    window.mainLayout.setSpacing(4)
    window.headerLayout.setContentsMargins(12, 4, 6, 4)
    window.headerLayout.setSpacing(8)
    for button, icon in ((window.settingsButton, "settings.svg"), (window.aboutButton, "about.svg")):
        button.setObjectName("headerIcon")
        button.setIcon(QIcon(str(ICONS / icon)))
        button.setIconSize(QSize(18, 18))
        button.setText("")
        button.setFixedSize(24, 22)

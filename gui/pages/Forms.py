"""Form, table and button building blocks shared by the device pages."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateTimeEdit,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from gui.Appearance import plainSpinBox

ROLE = Qt.ItemDataRole.UserRole
FIELD_MAX_WIDTH = 420
SETTINGS_COLUMN_WIDTH = 290
SLIDER_VALUE_WIDTH = 30


def setEnabledAll(widgets, enabled):
    for widget in widgets:
        widget.setEnabled(enabled)


def fieldLabel(text):
    label = QLabel(text)
    label.setObjectName("discoveryFieldLabel")
    return label


def formLayout(verticalSpacing=5):
    form = QFormLayout()
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    form.setHorizontalSpacing(10)
    form.setVerticalSpacing(verticalSpacing)
    return form


def addRow(form, label, widget):
    if isinstance(widget, (QLineEdit, QComboBox, QSpinBox, QDateTimeEdit)):
        widget.setMaximumWidth(FIELD_MAX_WIDTH)
    form.addRow(fieldLabel(label), widget)
    return widget


def valueRow(form, label):
    value = QLabel()
    value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    value.setWordWrap(True)
    return addRow(form, label, value)


def numberBox(minimum=None, maximum=None):
    box = plainSpinBox(QSpinBox())
    if minimum is not None:
        box.setRange(minimum, maximum)
    return box


def sliderRow(form, label):
    """Slider with its current value beside it; returns (slider, value label)."""
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    slider = QSlider(Qt.Orientation.Horizontal)
    value = QLabel()
    value.setMinimumWidth(SLIDER_VALUE_WIDTH)
    slider.valueChanged.connect(lambda number: value.setText(str(number)))
    row.addWidget(slider, 1)
    row.addWidget(value)
    addRow(form, label, holder)
    return slider, value


def section(layout, title):
    label = QLabel(title)
    label.setObjectName("discoverySection")
    layout.addWidget(label)
    return label


def summaryForm(layout, title):
    """Section heading followed by a compact form."""
    section(layout, title)
    form = formLayout(verticalSpacing=4)
    layout.addLayout(form)
    return form


def button(text, handler, primary=False):
    widget = QPushButton(text)
    if primary:
        widget.setObjectName("discoveryPrimary")
    widget.clicked.connect(handler)
    return widget


def buttonRow(layout, *buttons):
    row = QHBoxLayout()
    for widget in buttons:
        row.addWidget(widget)
    row.addStretch(1)
    layout.addLayout(row)


def applyCancelRow(layout, apply, cancel):
    buttonRow(layout, button("Apply", apply, primary=True), button("Cancel", cancel))


def pageLayout(page):
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    return layout


def settingsAndVideo(page):
    """Compact settings column on the left, live video on the right: (form, settings, video)."""
    columns = QHBoxLayout(page)
    columns.setContentsMargins(0, 0, 0, 0)
    columns.setSpacing(10)
    left = QWidget()
    left.setFixedWidth(SETTINGS_COLUMN_WIDTH)
    settings = QVBoxLayout(left)
    settings.setContentsMargins(0, 0, 0, 0)
    settings.setSpacing(6)
    form = QFormLayout()
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)  # label above its field
    form.setVerticalSpacing(3)
    settings.addLayout(form)
    video = QVBoxLayout()
    video.setSpacing(4)
    columns.addWidget(left)
    columns.addLayout(video, 1)
    return form, settings, video


def dataTable(columnCount):
    table = QTableWidget(0, columnCount)
    table.verticalHeader().hide()
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return table


def fillTable(table, records, cells, centered=()):
    """One row per record; cells(record) gives the column texts; each item carries its record."""
    table.setRowCount(0)
    for record in records:
        row = table.rowCount()
        table.insertRow(row)
        for column, value in enumerate(cells(record)):
            item = QTableWidgetItem(value)
            item.setData(ROLE, record)
            if column in centered:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, column, item)


def selectedRecord(table):
    items = table.selectedItems()
    return items[0].data(ROLE) if items else None

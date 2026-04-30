import math
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextOption, QFontMetricsF
from PyQt6.QtWidgets import (
    QWidget,
    QFrame,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QCheckBox,
)
from ...util.qt import BlockSignals, LayoutManager
from ...util import number_of_lines


class UiLayerId(QComboBox):
    def __init__(self, input, tooltip):
        super().__init__()

        self.input = input

        #self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setDuplicatesEnabled(True)

        self.activated.connect(self.on_changed)

        if tooltip is not None:
            self.setToolTip(tooltip)


    def on_changed(self):
        selected = self.selected()

        if selected is None:
            selected = ""

        self.input.set(selected)


    def add(self, text, data, icon=None):
        if icon is None:
            self.addItem(text, data)
        else:
            self.addItem(icon, text, data)


    def reset(self):
        with BlockSignals(self):
            value = self.input.get()

            if value is None or value == "":
                index = 0
            else:
                index = self.findData(value, flags=Qt.MatchFlag.MatchExactly)

            if self.currentIndex() != index:
                self.setCurrentIndex(index)


    def separator(self):
        self.insertSeparator(self.count())


    def selected(self):
        return self.currentData()


class UiString(QLineEdit):
    def __init__(self, input, placeholder, tooltip):
        super().__init__()

        self.input = input

        self.textEdited.connect(self.on_changed)

        if placeholder is not None:
            self.setPlaceholderText(placeholder)

        if tooltip is not None:
            self.setToolTip(tooltip)

    def on_changed(self):
        self.input.set(self.text())

    def reset(self):
        with BlockSignals(self):
            text = self.input.get()

            if text is None:
                text = ""

            self.setText(text)


class UiStringMultiline(QPlainTextEdit):
    def __init__(self, input, background_color, placeholder, tooltip, min_lines, max_lines):
        super().__init__()

        self.input = input
        self.min_lines = min_lines
        self.max_lines = max_lines

        self.textChanged.connect(self.on_changed)

        self.setTabChangesFocus(True)
        #self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        #self.setContentsMargins(0, 0, 0, 0)
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        #self.setFrameStyle(QFrame.Shape.NoFrame)

        if background_color is None:
            background_color = ""
        else:
            background_color = f"background-color: {background_color};"

        self.setStyleSheet(f"""
            QPlainTextEdit {{
                margin-left: 2px;
                margin-right: 2px;
                margin-top: 2px;
                margin-bottom: 2px;
                {background_color}
            }}
        """)

        self.setFixedHeight(self.get_pixel_height(self.min_lines))

        if placeholder is not None:
            self.setPlaceholderText(placeholder)

        if tooltip is not None:
            self.setToolTip(tooltip)

    def get_pixel_height(self, lines):
        metrics = QFontMetricsF(self.document().defaultFont())
        return math.ceil(metrics.lineSpacing() * (lines + 1))

    def resize(self, text):
        lines = max(self.min_lines, min(number_of_lines(text), self.max_lines))
        self.setFixedHeight(self.get_pixel_height(lines))

    def on_changed(self):
        text = self.toPlainText()
        self.resize(text)
        self.input.set(text)

    def reset(self):
        with BlockSignals(self):
            text = self.input.get()

            if text is None:
                text = ""

            self.resize(text)
            self.setPlainText(text)

    # This prevents the mouse wheel from scrolling the parent,
    # now it will only scroll the text box.
    def wheelEvent(self, event):
        super().wheelEvent(event)
        event.accept()


class UiGroup(QWidget):
    def __init__(self, input, title, default):
        super().__init__()

        self.input = input
        self.default = default

        self.layout_manager = LayoutManager(self)

        self.setContentsMargins(0, 4, 0, 4)

        with self.layout_manager.column() as column:
            with column.tool_button() as button:
                button.setStyleSheet("""
                    QToolButton {
                        background-color: transparent;
                        border: none;
                        padding: 0px;
                        margin: 0px;
                    }
                """)
                #button.setAutoRaise(True)
                button.setCheckable(True)
                button.setChecked(default)
                button.setText(title)
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                button.toggled.connect(self.on_toggled)
                self.toggle_button = button

            with column.widget(QWidget()) as widget:
                layout = LayoutManager(widget)
                self.container = widget

                with layout.column() as column:
                    # TODO figure out a way to calculate this automatically
                    column.set_padding(left=20)
                    self.layout = column

        self.update()


    def update(self):
        if self.toggle_button.isChecked():
            self.toggle_button.setArrowType(Qt.ArrowType.DownArrow)
            self.toggle_button.setToolTip("Close group...")
            self.container.show()

        else:
            self.toggle_button.setArrowType(Qt.ArrowType.RightArrow)
            self.toggle_button.setToolTip("Open group...")
            self.container.hide()


    def on_toggled(self, checked):
        self.input.set(checked)
        self.update()


    def reset(self):
        with BlockSignals(self):
            opened = self.input.get()

            if opened is None:
                opened = self.default

            if self.toggle_button.isChecked() != opened:
                self.toggle_button.setChecked(opened)
                self.update()


class UiRow(QWidget):
    def __init__(self):
        super().__init__()

        self.layout_manager = LayoutManager(self)

        with self.layout_manager.row() as row:
            self.layout = row

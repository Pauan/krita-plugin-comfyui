from PyQt6.QtCore import QObject, Qt
from PyQt6.QtWidgets import (
    QToolButton,
    QPushButton,
    QMessageBox,
    QTextEdit,
    QHBoxLayout,
    QVBoxLayout,
    QProgressBar,
    QLabel,
    QComboBox,
    QGroupBox,
    QScrollArea,
    QSizePolicy,
)


# Resizes to fit the detail text better
# https://stackoverflow.com/a/9969700/449477
class MessageBox(QMessageBox):
    def resizeEvent(self, event):
        result = super().resizeEvent(event)

        details_box = self.findChild(QTextEdit)
        if details_box is not None:
            details_box.setFixedSize(details_box.sizeHint())

        return result


class BlockSignals:
    def __init__(self, obj: QObject):
        self.obj = obj

    def __enter__(self):
        self.obj.blockSignals(True)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.obj.blockSignals(False)
        return False


class Scope:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def make_column():
    qlayout = QVBoxLayout()
    qlayout.setSpacing(0)
    qlayout.setContentsMargins(0, 0, 0, 0)
    return Layout(qlayout)


def make_row():
    qlayout = QHBoxLayout()
    qlayout.setSpacing(0)
    qlayout.setContentsMargins(0, 0, 0, 0)
    return Layout(qlayout)


class Layout:
    def __init__(self, qlayout):
        self.qlayout = qlayout
        self.widgets = []
        self.layouts = []


    def clear(self):
        for layout in self.layouts:
            layout.clear()

        while True:
            len = self.qlayout.count()

            if len > 0:
                item = self.qlayout.takeAt(len - 1)

                widget = item.widget()

                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()

            else:
                break

        self.widgets = []
        self.layouts = []


    def remove(self, widget):
        is_removed = False

        for layout in self.layouts:
            if layout.remove(widget):
                is_removed = True

        try:
            self.widgets.remove(widget)
        except ValueError:
            return is_removed

        # We only run this code if the widget is inside of self.widgets
        self.qlayout.removeWidget(widget)
        widget.setParent(None)
        widget.deleteLater()
        return True


    def set_child_spacing(self, amount):
        self.qlayout.setSpacing(amount)

    def set_padding(self, left=0, top=0, right=0, bottom=0):
        self.qlayout.setContentsMargins(left, top, right, bottom)


    def column(self):
        layout = make_column()
        self.qlayout.addLayout(layout.qlayout)
        self.layouts.append(layout)
        return Scope(layout)

    def row(self):
        layout = make_row()
        self.qlayout.addLayout(layout.qlayout)
        self.layouts.append(layout)
        return Scope(layout)


    def stretch(self, stretch=1):
        self.qlayout.addStretch(stretch)

    def spacer(self, amount):
        self.qlayout.addSpacing(amount)


    def widget(self, widget, stretch=0):
        self.qlayout.addWidget(widget, stretch)
        self.widgets.append(widget)
        return Scope(widget)


    def button(self, icon=None, text=None, cursor=Qt.CursorShape.PointingHandCursor, tooltip=None):
        widget = QPushButton()

        if icon is not None:
            widget.setIcon(icon)

        if text is not None:
            widget.setText(text)

        if cursor is not None:
            widget.setCursor(cursor)

        if tooltip is not None:
            widget.setToolTip(tooltip)

        return self.widget(widget)


    def tool_button(self, icon=None, text=None, cursor=Qt.CursorShape.PointingHandCursor, tooltip=None):
        widget = QToolButton()

        if icon is not None:
            widget.setIcon(icon)

        if text is not None:
            widget.setText(text)

        if cursor is not None:
            widget.setCursor(cursor)

        if tooltip is not None:
            widget.setToolTip(tooltip)

        return self.widget(widget)


    def progress_bar(self, minimum=None, maximum=None, tooltip=None):
        widget = QProgressBar()

        if minimum is not None:
            widget.setMinimum(minimum)

        if maximum is not None:
            widget.setMaximum(maximum)

        if tooltip is not None:
            widget.setToolTip(tooltip)

        return self.widget(widget)


    def label(self, icon=None, text=None, selectable=False, tooltip=None):
        widget = QLabel()

        if icon is not None:
            widget.setIcon(icon)

        if text is not None:
            widget.setText(text)

        if tooltip is not None:
            widget.setToolTip(tooltip)

        if selectable is True:
            widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)

        return self.widget(widget)


    def combo_box(self, cursor=Qt.CursorShape.PointingHandCursor, tooltip=None):
        widget = QComboBox()

        if tooltip is not None:
            widget.setToolTip(tooltip)

        if cursor is not None:
            widget.setCursor(cursor)

        return self.widget(widget)


    def group(self, title=None, align=None, flat=None, checkable=None, tooltip=None):
        widget = QGroupBox()

        if title is not None:
            widget.setTitle(title)

        if align is not None:
            widget.setAlignment(align)

        if flat is not None:
            widget.setFlat(flat)

        if checkable is not None:
            widget.setCheckable(checkable)

        if tooltip is not None:
            widget.setToolTip(tooltip)

        return self.widget(widget)


    def scroll(self, max_height=None):
        widget = QScrollArea()

        widget.setWidgetResizable(True)

        if max_height is not None:
            widget.setMaximumHeight(max_height)

        return self.widget(widget)


class LayoutManager:
    def __init__(self, parent):
        self.parent = parent
        self.layout = None


    def column(self):
        assert self.layout is None
        self.layout = make_column()
        self.parent.setLayout(self.layout.qlayout)
        return Scope(self.layout)


    def row(self):
        assert self.layout is None
        self.layout = make_row()
        self.parent.setLayout(self.layout.qlayout)
        return Scope(self.layout)

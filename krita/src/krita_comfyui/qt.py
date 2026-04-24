from PyQt6.QtWidgets import (
    QToolButton,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QProgressBar,
    QLabel,
)


class Scope:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class Layout:
    def __init__(self, parent):
        self.parent = parent
        self.widgets = []
        self.layouts = []

    def column(self):
        layout = QVBoxLayout(self.parent)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        self.layouts.append(layout)
        return Scope(layout)

    def row(self):
        layout = QHBoxLayout(self.parent)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        self.layouts.append(layout)
        return Scope(layout)

    def button(self):
        widget = QPushButton(self.parent)
        self.widgets.append(widget)
        return Scope(widget)

    def tool_button(self):
        widget = QToolButton(self.parent)
        self.widgets.append(widget)
        return Scope(widget)

    def progress_bar(self):
        widget = QProgressBar(self.parent)
        self.widgets.append(widget)
        return Scope(widget)

    def label(self):
        widget = QLabel(self.parent)
        self.widgets.append(widget)
        return Scope(widget)

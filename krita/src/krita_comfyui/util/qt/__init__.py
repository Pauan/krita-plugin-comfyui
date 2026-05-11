import re
import math
from PyQt6.QtCore import QObject, QSortFilterProxyModel, QRegularExpression, QSize, QEvent, Qt
from PyQt6.QtGui import QFontMetricsF
from PyQt6.QtWidgets import (
    QToolButton,
    QPushButton,
    QMessageBox,
    QTextEdit,
    QHBoxLayout,
    QVBoxLayout,
    QProgressBar,
    QToolBar,
    QLabel,
    QComboBox,
    QGroupBox,
    QSlider,
    QSpinBox,
    QDoubleSpinBox,
    QScrollArea,
    QSizePolicy,
    QCompleter,
)


RE_SPACE = re.compile(r" +")

"""
    Custom QCompleter that allows for matching substrings.

    The string `foo bar qux` will match substring of `foo` followed by substring of `bar` followed by substring of `qux`.
"""
class Completer(QCompleter):
    def splitPath(self, path):
        self.model().setFilterRegularExpression(r".*\b.*".join(QRegularExpression.escape(x) for x in re.split(RE_SPACE, path.strip())))
        return []


class ComboBox(QComboBox):
    def __init__(self, *args):
        super().__init__(*args)

        self.block_wheel = BlockMouseWheel(self)
        self.installEventFilter(self.block_wheel)

        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setDuplicatesEnabled(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        model = QSortFilterProxyModel(self)
        model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        model.setSourceModel(self.completer().model())

        completer = Completer(model, self)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)

        self.setCompleter(completer)


    # Resizes the dropdown so it fits all of the items
    def resize_dropdown(self):
        view = self.view()

        icon_size = max(0, self.iconSize().width())
        has_icon = False

        for i in range(self.count()):
            icon = self.itemIcon(i)
            if icon is not None and not icon.isNull():
                has_icon = True

        if not has_icon:
            icon_size = 0

        column_width = max(0, view.sizeHintForColumn(0))

        scrollbar_width = max(0, view.verticalScrollBar().sizeHint().width())

        view.setMinimumWidth(icon_size + column_width + scrollbar_width)


# This causes the mouse wheel event to be blocked, but only when Shift / Alt / Ctrl are not being pressed.
class BlockMouseWheel(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            modifiers = event.modifiers()

            if modifiers == Qt.KeyboardModifier.NoModifier:
                event.ignore()
                return True

        return super().eventFilter(obj, event)


class Slider(QSlider):
    def __init__(self, *args):
        super().__init__(*args)
        self.block_wheel = BlockMouseWheel(self)
        self.installEventFilter(self.block_wheel)


class SpinBox(QSpinBox):
    def __init__(self, *args):
        super().__init__(*args)
        self.block_wheel = BlockMouseWheel(self)
        self.installEventFilter(self.block_wheel)


class DoubleSpinBox(QDoubleSpinBox):
    def __init__(self, *args):
        super().__init__(*args)
        self.block_wheel = BlockMouseWheel(self)
        self.installEventFilter(self.block_wheel)


# Resizes to fit the detail text better
# https://stackoverflow.com/a/9969700/449477
class MessageBox(QMessageBox):
    pass

    #def resizeEvent(self, event):
        #result = super().resizeEvent(event)

        #details_box = self.findChild(QTextEdit)
        #if details_box is not None:
            #details_box.setFixedSize(details_box.sizeHint())

        #return result


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


class Toolbar:
    def __init__(self, qtoolbar):
        self.qtoolbar = qtoolbar


    def widget(self, widget):
        self.qtoolbar.addWidget(widget)
        return Scope(widget)


    # TODO code duplication with Layout
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


    def separator(self):
        return Scope(self.qtoolbar.addSeparator())


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


    def toolbar(self, orientation=Qt.Orientation.Horizontal, tooltip=None):
        widget = QToolBar()

        widget.setOrientation(orientation)
        widget.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        widget.setIconSize(QSize(16, 16))
        widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        widget.setContentsMargins(0, 0, 0, 0)

        if tooltip is not None:
            widget.setToolTip(tooltip)

        with self.widget(widget) as widget:
            return Scope(Toolbar(widget))


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
        widget = ComboBox()

        if tooltip is not None:
            widget.setToolTip(tooltip)

        if cursor is not None:
            widget.setCursor(cursor)

        return self.widget(widget)


    def slider(self, tooltip=None):
        widget = Slider()

        if tooltip is not None:
            widget.setToolTip(tooltip)

        return self.widget(widget)


    def int(self, tooltip=None):
        widget = SpinBox()

        if tooltip is not None:
            widget.setToolTip(tooltip)

        return self.widget(widget)


    def float(self, tooltip=None):
        widget = DoubleSpinBox()

        if tooltip is not None:
            widget.setToolTip(tooltip)

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

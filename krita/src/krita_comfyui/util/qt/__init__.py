from __future__ import annotations

import re
import contextlib
import traceback
import builtins
from collections.abc import Generator, Sequence
from types import TracebackType
from typing import Literal, Protocol, cast
from PyQt6.QtCore import QObject, QThread, QSortFilterProxyModel, QRegularExpression, QSize, QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QGuiApplication, QIcon, QKeyEvent, QWheelEvent, QShowEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QWidget,
    QMenu,
    QWidgetAction,
    QCheckBox,
    QToolButton,
    QPushButton,
    QMessageBox,
    QHBoxLayout,
    QVBoxLayout,
    QProgressBar,
    QToolBar,
    QListWidget,
    QLabel,
    QComboBox,
    QGroupBox,
    QSlider,
    QSpinBox,
    QDoubleSpinBox,
    QScrollArea,
    QSizePolicy,
    QCompleter,
    QStackedLayout,
    QBoxLayout,
)
from .toggle import Toggle


RE_SPACE = re.compile(r" +")

"""
    Custom QCompleter that allows for matching substrings.

    The string `foo bar qux` will match substring of `foo` followed by substring of `bar` followed by substring of `qux`.
"""
class Completer(QCompleter):
    def splitPath(self, path: str | None) -> list[str]:
        model = cast(QSortFilterProxyModel, self.model())
        model.setFilterRegularExpression(r".*\b.*".join([QRegularExpression.escape(x) for x in re.split(RE_SPACE, (path or "").strip())]))
        return []


# This causes the mouse wheel event to be blocked, but only when Shift / Alt / Ctrl are not being pressed.
class BlockMouseWheel(QObject):
    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        if isinstance(a1, QWheelEvent):
            modifiers = a1.modifiers()

            if modifiers == Qt.KeyboardModifier.NoModifier:
                a1.ignore()
                return True

        return super().eventFilter(a0, a1)


# This causes the up / down keys to be ignored and proxied to another widget.
class BlockKeyUpDown(QObject):
    def __init__(self, parent: QObject | None, proxy: QObject) -> None:
        super().__init__(parent)
        self.proxy = proxy

    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        if isinstance(a1, QKeyEvent) and a1.type() == QEvent.Type.KeyPress:
            if a1.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                QGuiApplication.sendEvent(self.proxy, a1)
                return True

        return super().eventFilter(a0, a1)


class Thread(QThread):
    def __init__(self, parent: QObject | None) -> None:
        super().__init__(parent)
        self.objects: list[QObject] = []


    def move(self, object: QObject) -> None:
        self.objects.append(object)
        object.moveToThread(self)


    @contextlib.contextmanager
    def stop(self) -> Generator[None]:
        try:
            for x in self.objects:
                x.deleteLater()

        finally:
            self.quit()

            # This causes it to schedule all of the waits at the same time.
            yield

            self.wait()


class MessageBox(QMessageBox):
    def __init__(
        self,
        parent: QWidget | None,
        *,
        text: str,
        icon: QMessageBox.Icon | None = None,
        information: str | None = None,
        details: str | None = None,
        rich_text: bool = False,
        buttons: Sequence[QMessageBox.StandardButton] = (),
    ) -> None:
        super().__init__(parent)

        if rich_text:
            self.setTextFormat(Qt.TextFormat.RichText)
        else:
            self.setTextFormat(Qt.TextFormat.PlainText)

        if icon is None:
            self.setIcon(QMessageBox.Icon.NoIcon)
        else:
            self.setIcon(icon)

        self.setSizeGripEnabled(True)
        self.setWindowTitle("Krita ComfyUI Plugin")
        self.setText(text)

        if information is not None:
            self.setInformativeText(information)

        if details is not None:
            self.setDetailedText(details)

        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.LinksAccessibleByMouse |
            Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )

        for button in buttons:
            self.addButton(button)

        self.exec()


    @staticmethod
    def question(parent: QWidget | None, text: str) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
        reply = QMessageBox.question(parent, "Krita Plugin ComfyUI", text)
        return reply == QMessageBox.StandardButton.Yes


    @staticmethod
    def info(parent: QWidget | None, *, text: str, information: str | None = None, details: str | None = None, rich_text: bool = False) -> None:
        MessageBox(parent,
            icon=QMessageBox.Icon.Information,
            text=text,
            information=information,
            details=details,
            rich_text=rich_text,
            buttons=[QMessageBox.StandardButton.Ok],
        )


    @staticmethod
    def error(parent: QWidget | None, *, text: str, information: str | None = None, details: str | None = None, rich_text: bool = False) -> None:
        MessageBox(parent,
            icon=QMessageBox.Icon.Critical,
            text=text,
            information=information,
            details=details,
            rich_text=rich_text,
            buttons=[QMessageBox.StandardButton.Ok],
        )


    @staticmethod
    def from_exception(parent: QWidget | None, exception: BaseException) -> None:
        MessageBox(parent,
            icon=QMessageBox.Icon.Critical,
            text=str(exception),
            details="".join(traceback.format_exception(exception)),
            buttons=[QMessageBox.StandardButton.Ok],
        )


    # Resizes to fit the detail text better
    # https://stackoverflow.com/a/9969700/449477
    #def resizeEvent(self, event):
        #result = super().resizeEvent(event)

        #details_box = self.findChild(QTextEdit)
        #if details_box is not None:
            #details_box.setFixedSize(details_box.sizeHint())

        #return result


class ScrollArea(QScrollArea):
    def sizeHint(self) -> QSize:
        frame = self.frameWidth() * 2

        if self.verticalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff:
            vertical_scroll_bar = self.verticalScrollBar()
            assert vertical_scroll_bar is not None
            width = vertical_scroll_bar.sizeHint().width()
        else:
            width = 0

        if self.horizontalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff:
            horizontal_scroll_bar = self.horizontalScrollBar()
            assert horizontal_scroll_bar is not None
            height = horizontal_scroll_bar.sizeHint().height()
        else:
            height = 0

        widget = self.widget()
        assert widget is not None

        return QSize(frame, frame) + widget.sizeHint() + QSize(width, height)


class MenuWidget(Protocol):
    def on_menu_show(self) -> None: ...
    def adjustSize(self) -> None: ...
    def size(self) -> QSize: ...


class Menu(QMenu):
    def __init__(self, parent: QWidget | None, widget: MenuWidget) -> None:
        super().__init__(parent)

        self.widget = widget

        self.action = QWidgetAction(self)
        self.action.setDefaultWidget(cast(QWidget, self.widget))
        self.action.setMenuRole(QAction.MenuRole.NoRole)
        self.addAction(self.action)


    def refresh_size(self) -> None:
        self.widget.on_menu_show()
        self.widget.adjustSize()

        # TODO figure out an automatic way of finding the margin size
        self.resize(self.widget.size() + QSize(8, 8))


    # This causes it to not close the menu when clicking inside the menu.
    def mouseReleaseEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is not None:
            a0.ignore()


    def showEvent(self, a0: QShowEvent | None) -> None:
        super().showEvent(a0)
        self.refresh_size()


class ComboBox(QComboBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.block_wheel = BlockMouseWheel(self)
        self.installEventFilter(self.block_wheel)

        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setDuplicatesEnabled(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        model = QSortFilterProxyModel(self)
        model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer = self.completer()
        assert completer is not None
        model.setSourceModel(completer.model())

        completer = Completer(model, self)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)

        self.setCompleter(completer)


    # Resizes the dropdown automatically when it's displayed.
    def showEvent(self, e: QShowEvent | None) -> None:
        super().showEvent(e)
        self.resize_dropdown()


    # Resizes the dropdown so it fits all of the items
    def resize_dropdown(self) -> None:
        view = self.view()
        assert view is not None

        icon_size = max(0, self.iconSize().width())
        has_icon = False

        for i in range(self.count()):
            icon = self.itemIcon(i)
            if icon is not None and not icon.isNull(): # pyright: ignore[reportUnnecessaryComparison]
                has_icon = True

        if not has_icon:
            icon_size = 0

        column_width = max(0, view.sizeHintForColumn(0))

        vertical_scroll_bar = view.verticalScrollBar()
        assert vertical_scroll_bar is not None

        scrollbar_width = max(0, vertical_scroll_bar.sizeHint().width())

        view.setMinimumWidth(icon_size + column_width + scrollbar_width)


class BooleanSwitch(QWidget):
    changed = pyqtSignal(Qt.CheckState)
    checkbox: QCheckBox

    def __init__(self, tooltip: str, label: str | None, style: str) -> None:
        super().__init__()

        self.layout_manager = LayoutManager(self)

        with self.layout_manager.row() as row:
            if style == "switch":
                with row.widget(Toggle()) as checkbox:
                    self.checkbox = checkbox
                    checkbox.checkStateChanged.connect(self.changed)

                if label is not None:
                    row.label(text=label)

            elif style == "checkbox":
                with row.widget(QCheckBox()) as checkbox:
                    self.checkbox = checkbox
                    checkbox.checkStateChanged.connect(self.changed)
                    checkbox.setStyleSheet("""
                        QCheckBox {
                            spacing: 4px;
                        }
                        QCheckBox::indicator {
                            width: 24px;
                            height: 24px;
                        }
                    """)

                    if label is not None:
                        checkbox.setText(label)

            else:
                raise RuntimeError("style must be switch or checkbox")

        self.setFixedHeight(32)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


    def isChecked(self) -> bool:
        return self.checkbox.isChecked()


    def setChecked(self, checked: bool) -> None:
        if self.checkbox.isChecked() != checked:
            self.checkbox.setChecked(checked)


    # TODO this should be mouseClickEvent but it doesn't exist!
    def mousePressEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is not None and a0.button() == Qt.MouseButton.LeftButton:
            self.checkbox.setChecked(not self.checkbox.isChecked())
        super().mousePressEvent(a0)


class Slider(QSlider):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.block_wheel = BlockMouseWheel(self)
        self.installEventFilter(self.block_wheel)


class SpinBox(QSpinBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.block_wheel = BlockMouseWheel(self)
        self.installEventFilter(self.block_wheel)


class DoubleSpinBox(QDoubleSpinBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.block_wheel = BlockMouseWheel(self)
        self.installEventFilter(self.block_wheel)


class BlockSignals:
    def __init__(self, obj: QObject) -> None:
        self.obj = obj

    def __enter__(self) -> None:
        self.obj.blockSignals(True)

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None) -> Literal[False]:
        self.obj.blockSignals(False)
        return False


class Scope[T]:
    def __init__(self, value: T) -> None:
        self.value = value

    def __enter__(self) -> T:
        return self.value

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None) -> Literal[False]:
        return False


def make_column() -> Layout:
    qlayout = QVBoxLayout()
    qlayout.setSpacing(0)
    qlayout.setContentsMargins(0, 0, 0, 0)
    return Layout(qlayout)


def make_row() -> Layout:
    qlayout = QHBoxLayout()
    qlayout.setSpacing(0)
    qlayout.setContentsMargins(0, 0, 0, 0)
    return Layout(qlayout)


def make_stack() -> Layout:
    qlayout = QStackedLayout()
    qlayout.setSpacing(0)
    qlayout.setContentsMargins(0, 0, 0, 0)
    return Layout(qlayout)


class Toolbar:
    def __init__(self, qtoolbar: QToolBar) -> None:
        self.qtoolbar = qtoolbar


    def widget[W: QWidget](self, widget: W) -> Scope[W]:
        self.qtoolbar.addWidget(widget)
        return Scope(widget)


    # TODO code duplication with Layout
    def tool_button(self, icon: QIcon | None = None, text: str | None = None, cursor: Qt.CursorShape | None = Qt.CursorShape.PointingHandCursor, tooltip: str | None = None) -> Scope[QToolButton]:
        widget = QToolButton()

        if icon is not None:
            widget.setIcon(icon)

        if text is not None:
            widget.setText(text)
            widget.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        if cursor is not None:
            widget.setCursor(cursor)

        if tooltip is not None:
            widget.setToolTip(tooltip)

        return self.widget(widget)


    def separator(self) -> Scope[QAction]:
        action = self.qtoolbar.addSeparator()
        assert action is not None
        return Scope(action)


class Layout:
    def __init__(self, qlayout: QBoxLayout | QStackedLayout) -> None:
        self.qlayout = qlayout
        self.widgets: list[QWidget] = []
        self.layouts: list[Layout] = []


    def clear(self) -> None:
        for layout in self.layouts:
            layout.clear()

        while True:
            len = self.qlayout.count()

            if len > 0:
                item = self.qlayout.takeAt(len - 1)

                if item is not None:
                    widget = item.widget()

                    if widget is not None:
                        widget.setParent(None)
                        widget.deleteLater()

            else:
                break

        self.widgets = []
        self.layouts = []


    def remove(self, widget: QWidget) -> bool:
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


    def set_child_spacing(self, amount: builtins.int) -> None:
        self.qlayout.setSpacing(amount)

    def set_padding(self, left: builtins.int = 0, top: builtins.int = 0, right: builtins.int = 0, bottom: builtins.int = 0) -> None:
        self.qlayout.setContentsMargins(left, top, right, bottom)

    def set_current_index(self, index: builtins.int) -> None:
        assert isinstance(self.qlayout, QStackedLayout)
        self.qlayout.setCurrentIndex(index)

    def current_widget(self) -> QWidget | None:
        assert isinstance(self.qlayout, QStackedLayout)
        return self.qlayout.currentWidget()


    def _add_layout(self, layout: Layout, stretch: builtins.int) -> None:
        assert isinstance(self.qlayout, QBoxLayout)

        if stretch == 0:
            self.qlayout.addLayout(layout.qlayout)
        else:
            self.qlayout.addLayout(layout.qlayout, stretch)


    def column(self, *, stretch: builtins.int = 0, align: Qt.AlignmentFlag | None = None) -> Scope[Layout]:
        layout = make_column()

        self._add_layout(layout, stretch)

        if align is not None:
            assert self.qlayout.setAlignment(layout.qlayout, align)

        self.layouts.append(layout)
        return Scope(layout)


    def row(self, *, stretch: builtins.int = 0, align: Qt.AlignmentFlag | None = None) -> Scope[Layout]:
        layout = make_row()

        self._add_layout(layout, stretch)

        if align is not None:
            assert self.qlayout.setAlignment(layout.qlayout, align)

        self.layouts.append(layout)
        return Scope(layout)


    def stack(self, *, stretch: builtins.int = 0, align: Qt.AlignmentFlag | None = None) -> Scope[Layout]:
        layout = make_stack()

        self._add_layout(layout, stretch)

        if align is not None:
            assert self.qlayout.setAlignment(layout.qlayout, align)

        self.layouts.append(layout)
        return Scope(layout)


    def stretch(self, stretch: builtins.int = 1) -> None:
        assert isinstance(self.qlayout, QBoxLayout)
        self.qlayout.addStretch(stretch)

    def spacer(self, amount: builtins.int) -> None:
        assert isinstance(self.qlayout, QBoxLayout)
        self.qlayout.addSpacing(amount)


    def widget[W: QWidget](self, widget: W, *, stretch: builtins.int = 0) -> Scope[W]:
        if stretch == 0:
            self.qlayout.addWidget(widget)
        else:
            assert isinstance(self.qlayout, QBoxLayout)
            self.qlayout.addWidget(widget, stretch)
        self.widgets.append(widget)
        return Scope(widget)


    def list(self) -> Scope[QListWidget]:
        return self.widget(QListWidget())


    def button(self, *, stretch: builtins.int = 0, icon: QIcon | None = None, text: str | None = None, cursor: Qt.CursorShape | None = Qt.CursorShape.PointingHandCursor, tooltip: str | None = None) -> Scope[QPushButton]:
        widget = QPushButton()

        if icon is not None:
            widget.setIcon(icon)

        if text is not None:
            widget.setText(text)

        if cursor is not None:
            widget.setCursor(cursor)

        if tooltip is not None:
            widget.setToolTip(tooltip)

        return self.widget(widget, stretch=stretch)


    def toolbar(self, *, stretch: builtins.int = 0, orientation: Qt.Orientation = Qt.Orientation.Horizontal, tooltip: str | None = None) -> Scope[Toolbar]:
        widget = QToolBar()

        widget.setOrientation(orientation)
        widget.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        widget.setIconSize(QSize(16, 16))
        widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        widget.setContentsMargins(0, 0, 0, 0)

        widget.setStyleSheet("""
            QToolBar {
                padding: 0px;
                margin: 3px;
            }
        """)

        if tooltip is not None:
            widget.setToolTip(tooltip)

        with self.widget(widget, stretch=stretch) as widget:
            return Scope(Toolbar(widget))


    def tool_button(self, *, stretch: builtins.int = 0, icon: QIcon | None = None, text: str | None = None, cursor: Qt.CursorShape | None = Qt.CursorShape.PointingHandCursor, tooltip: str | None = None) -> Scope[QToolButton]:
        widget = QToolButton()

        if icon is not None:
            widget.setIcon(icon)

        if text is not None:
            widget.setText(text)
            widget.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        if cursor is not None:
            widget.setCursor(cursor)

        if tooltip is not None:
            widget.setToolTip(tooltip)

        return self.widget(widget, stretch=stretch)


    def progress_bar(self, *, stretch: builtins.int = 0, minimum: builtins.int | None = None, maximum: builtins.int | None = None, tooltip: str | None = None) -> Scope[QProgressBar]:
        widget = QProgressBar()

        if minimum is not None:
            widget.setMinimum(minimum)

        if maximum is not None:
            widget.setMaximum(maximum)

        if tooltip is not None:
            widget.setToolTip(tooltip)

        return self.widget(widget, stretch=stretch)


    def icon(self, icon: QIcon | None, *, width: builtins.int, height: builtins.int, stretch: builtins.int = 0, tooltip: str | None = None) -> Scope[QLabel]:
        widget = QLabel()

        if icon is not None:
            widget.setPixmap(icon.pixmap(QSize(width, height)))

        if tooltip is not None:
            widget.setToolTip(tooltip)

        return self.widget(widget, stretch=stretch)


    def label(self, *, stretch: builtins.int = 0, text: str | None = None, selectable: bool = False, tooltip: str | None = None) -> Scope[QLabel]:
        widget = QLabel()

        if text is not None:
            widget.setText(text)

        if tooltip is not None:
            widget.setToolTip(tooltip)

        if selectable is True:
            widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)

        return self.widget(widget, stretch=stretch)


    def combo_box(self, *, stretch: builtins.int = 0, cursor: Qt.CursorShape | None = Qt.CursorShape.PointingHandCursor, tooltip: str | None = None) -> Scope[ComboBox]:
        widget = ComboBox()

        if tooltip is not None:
            widget.setToolTip(tooltip)

        if cursor is not None:
            widget.setCursor(cursor)

        return self.widget(widget, stretch=stretch)


    def slider(self, *, stretch: builtins.int = 0, tooltip: str | None = None) -> Scope[Slider]:
        widget = Slider()

        if tooltip is not None:
            widget.setToolTip(tooltip)

        return self.widget(widget, stretch=stretch)


    def int(self, *, stretch: builtins.int = 0, tooltip: str | None = None) -> Scope[SpinBox]:
        widget = SpinBox()

        if tooltip is not None:
            widget.setToolTip(tooltip)

        return self.widget(widget, stretch=stretch)


    def float(self, *, stretch: builtins.int = 0, tooltip: str | None = None) -> Scope[DoubleSpinBox]:
        widget = DoubleSpinBox()

        if tooltip is not None:
            widget.setToolTip(tooltip)

        return self.widget(widget, stretch=stretch)


    def group(self, *, stretch: builtins.int = 0, title: str | None = None, align: Qt.AlignmentFlag | None = None, flat: bool | None = None, checkable: bool | None = None, tooltip: str | None = None) -> Scope[QGroupBox]:
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

        return self.widget(widget, stretch=stretch)


    def scroll(self, *, stretch: builtins.int = 0, max_height: builtins.int | None = None) -> Scope[QScrollArea]:
        widget = QScrollArea()

        widget.setWidgetResizable(True)

        if max_height is not None:
            widget.setMaximumHeight(max_height)

        return self.widget(widget, stretch=stretch)


class LayoutManager:
    def __init__(self, parent: QWidget) -> None:
        self.parent = parent
        self.layout: Layout | None = None


    def column(self) -> Scope[Layout]:
        assert self.layout is None
        layout = self.layout = make_column()
        self.parent.setLayout(layout.qlayout)
        return Scope(layout)


    def row(self) -> Scope[Layout]:
        assert self.layout is None
        layout = self.layout = make_row()
        self.parent.setLayout(layout.qlayout)
        return Scope(layout)


    def stack(self) -> Scope[Layout]:
        assert self.layout is None
        layout = self.layout = make_stack()
        self.parent.setLayout(layout.qlayout)
        return Scope(layout)

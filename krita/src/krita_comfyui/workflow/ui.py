from krita import SliderSpinBox, DoubleSliderSpinBox
import math
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QTextOption, QFontMetricsF
from PyQt6.QtWidgets import (
    QWidget,
    QFrame,
    QLineEdit,
    QPlainTextEdit,
    QCheckBox,
    QMessageBox,
    QSizePolicy,
)
from ..util.qt import BlockSignals, LayoutManager, ComboBox, BlockMouseWheel
from ..util import number_of_lines, lerp, normalize, clamp


class UiLayerId(ComboBox):
    def __init__(self, input, layers, tooltip):
        super().__init__()

        self.input = input

        self.activated.connect(self.on_changed)

        self.setToolTip(self.input.format_tooltip(tooltip))

        self.set_layers(layers)


    def on_changed(self):
        selected = self.currentData()

        if selected is None:
            selected = ""

        self.input.set(selected)


    def set_layers(self, layers):
        with BlockSignals(self):
            self.clear()

            self.addItem("", "")

            for layer in layers:
                if layer is None:
                    self.insertSeparator(self.count())
                else:
                    self.addItem(layer.type.icon(), layer.name, layer.id)

            selected_id = self.input.get()

            if selected_id == "":
                index = 0
            else:
                index = self.findData(selected_id, flags=Qt.MatchFlag.MatchExactly)

            if self.currentIndex() != index:
                self.setCurrentIndex(index)

            self.resize_dropdown()


class UiCombo(ComboBox):
    def __init__(self, input, tooltip, values):
        super().__init__()

        self.input = input

        self.activated.connect(self.on_changed)

        self.setToolTip(self.input.format_tooltip(tooltip))

        self.set_values(values)


    def on_changed(self):
        selected = self.currentText()
        assert selected is not None
        self.input.set(selected)


    def set_values(self, values):
        with BlockSignals(self):
            self.clear()

            self.addItem("")

            for value in values:
                self.addItem(value)

            selected_value = self.input.get()

            if selected_value == "":
                index = 0
            else:
                index = self.findText(selected_value, flags=Qt.MatchFlag.MatchExactly)

            if self.currentIndex() != index:
                self.setCurrentIndex(index)

            self.resize_dropdown()


class UiBoolean(QCheckBox):
    def __init__(self, input, tooltip, label):
        super().__init__()

        self.input = input

        self.setChecked(self.input.get())

        self.setStyleSheet("""
            QCheckBox {
                spacing: 4px;
            }
            QCheckBox::indicator {
                width: 24px;
                height: 24px;
            }
        """)

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

        if label is not None:
            self.setText(label)

        self.checkStateChanged.connect(self.on_changed)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self.input.format_tooltip(tooltip))

    def on_changed(self):
        self.input.set(self.isChecked())


class UiString(QLineEdit):
    def __init__(self, input, placeholder, tooltip):
        super().__init__()

        self.input = input

        self.setText(self.input.get())

        self.textEdited.connect(self.on_changed)

        if placeholder is not None:
            self.setPlaceholderText(placeholder)

        self.setToolTip(self.input.format_tooltip(tooltip))

    def on_changed(self):
        self.input.set(self.text())


class UiStringMultiline(QPlainTextEdit):
    def __init__(self, input, background_color, placeholder, tooltip, min_lines, max_lines):
        super().__init__()

        self.input = input
        self.min_lines = min_lines
        self.max_lines = max_lines

        self.set_text(self.input.get())

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

        self.setToolTip(self.input.format_tooltip(tooltip))

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

    def set_text(self, text):
        self.resize(text)
        self.setPlainText(text)

    def wheelEvent(self, event):
        super().wheelEvent(event)

        scrollbar = self.verticalScrollBar()

        # If we have a vertical scrollbar, then this prevents the mouse wheel
        # from scrolling the parent, now it will only scroll the text box.
        if scrollbar is not None and scrollbar.isVisible():
            event.accept()


class UiGroup(QWidget):
    def __init__(self, input, title):
        super().__init__()

        self.input = input

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
                button.setChecked(self.input.get())
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
        if self.input.default == checked:
            self.input.reset_to_default()
        else:
            self.input.set(checked)

        self.update()


class UiRow(QWidget):
    def __init__(self):
        super().__init__()

        self.layout_manager = LayoutManager(self)

        with self.layout_manager.row() as row:
            self.layout = row


class UiFloat(QWidget):
    def __init__(self, input, slider, tooltip, min, max, step, decimals, multiplier, prefix, suffix):
        super().__init__()

        self.input = input
        self.min = min
        self.max = max
        self.step = step
        self.decimals = decimals
        self.multiplier = multiplier

        if self.multiplier is None:
            self.multiplier = 1.0

        self.setToolTip(self.input.format_tooltip(tooltip))

        self.layout_manager = LayoutManager(self)

        display_value = round(clamp(self.input.get(), self.min, self.max) * self.multiplier, self.decimals)

        # TODO maybe we don't need a LayoutManager ?
        with self.layout_manager.column() as column:
            if slider:
                # This blocks the slider from receiving the mouse wheel event
                self.block_wheel = BlockMouseWheel(self)

                self.slider = DoubleSliderSpinBox()
                self.slider.setParent(self)

                self.slider.setFastSliderStep(self.step * self.multiplier)
                self.slider.setRange(self.min * self.multiplier, self.max * self.multiplier, self.decimals)

                with column.widget(self.slider.widget()) as widget:
                    if prefix is not None:
                        widget.setPrefix(prefix)

                    if suffix is not None:
                        widget.setSuffix(suffix)

                    widget.installEventFilter(self.block_wheel)

                    widget.setSingleStep(self.step * self.multiplier)
                    widget.setValue(display_value)
                    widget.draggingFinished.connect(self.on_drag_end)
                    widget.valueChanged.connect(self.on_value_changed)
                    self.value_widget = widget

            else:
                self.block_wheel = None
                self.slider = None

                with column.float() as widget:
                    if prefix is not None:
                        widget.setPrefix(prefix)

                    if suffix is not None:
                        widget.setSuffix(suffix)

                    widget.setRange(min * self.multiplier, max * self.multiplier)
                    widget.setSingleStep(step * self.multiplier)
                    widget.setDecimals(self.decimals)
                    widget.setValue(display_value)
                    widget.valueChanged.connect(self.on_value_changed)
                    self.value_widget = widget


    def get_real_value(self):
        value = round(self.value_widget.value(), self.decimals) / self.multiplier
        return clamp(value, self.min, self.max)


    def clamp_to_step(self):
        value = self.get_real_value()

        # Rounds to the nearest step
        new_value = round(value / self.step) * self.step

        # The rounding is to prevent floating point rounding errors
        # like 0.3 becoming 0.30000000000000004
        # TODO make the rounding configurable
        new_value = clamp(round(new_value, 10), self.min, self.max)

        if value != new_value:
            value = new_value
            self.value_widget.setValue(round(value * self.multiplier, self.decimals))

        return value


    # Normally the valueChanged event handles clamping, but in the rare
    # (impossible?) situation where the draggingFinished event triggers
    # before the valueChanged event, we do some extra clamping in here.
    def on_drag_end(self):
        self.clamp_to_step()


    def on_value_changed(self, _):
        # We want to clamp the value while dragging, but the draggingFinished event
        # only triggers when the dragging is ended, so we have to clamp in here.
        if self.slider is not None and self.slider.isDragging():
            with BlockSignals(self.value_widget):
                value = self.clamp_to_step()
        else:
            value = self.get_real_value()

        self.input.set(value)


class UiInt(QWidget):
    def __init__(self, input, slider, tooltip, min, max, step, prefix, suffix):
        super().__init__()

        self.input = input
        self.min = min
        self.max = max
        self.step = step

        self.setToolTip(self.input.format_tooltip(tooltip))

        self.layout_manager = LayoutManager(self)

        # TODO maybe we don't need a LayoutManager ?
        with self.layout_manager.column() as column:
            if slider:
                # This blocks the slider from receiving the mouse wheel event
                self.block_wheel = BlockMouseWheel(self)

                self.slider = SliderSpinBox()
                self.slider.setParent(self)

                self.slider.setFastSliderStep(step)
                self.slider.setRange(min, max)

                with column.widget(self.slider.widget()) as widget:
                    if prefix is not None:
                        widget.setPrefix(prefix)

                    if suffix is not None:
                        widget.setSuffix(suffix)

                    widget.installEventFilter(self.block_wheel)

                    widget.setSingleStep(step)
                    widget.setValue(clamp(self.input.get(), min, max))
                    widget.draggingFinished.connect(self.on_drag_end)
                    widget.valueChanged.connect(self.on_value_changed)
                    self.value_widget = widget

            else:
                self.block_wheel = None
                self.slider = None

                with column.int() as widget:
                    if prefix is not None:
                        widget.setPrefix(prefix)

                    if suffix is not None:
                        widget.setSuffix(suffix)

                    widget.setRange(min, max)
                    widget.setSingleStep(step)
                    widget.setValue(clamp(self.input.get(), min, max))
                    widget.valueChanged.connect(self.on_value_changed)
                    self.value_widget = widget


    def get_real_value(self):
        return clamp(self.value_widget.value(), self.min, self.max)


    def clamp_to_step(self):
        value = self.get_real_value()

        # Rounds to the nearest step
        new_value = round(float(value) / float(self.step)) * self.step
        new_value = clamp(new_value, self.min, self.max)

        if value != new_value:
            value = new_value
            self.value_widget.setValue(value)

        return value


    # Normally the valueChanged event handles clamping, but in the rare
    # (impossible?) situation where the draggingFinished event triggers
    # before the valueChanged event, we do some extra clamping in here.
    def on_drag_end(self):
        self.clamp_to_step()


    def on_value_changed(self, _):
        # We want to clamp the value while dragging, but the draggingFinished event
        # only triggers when the dragging is ended, so we have to clamp in here.
        if self.slider is not None and self.slider.isDragging():
            with BlockSignals(self.value_widget):
                value = self.clamp_to_step()
        else:
            value = self.get_real_value()

        self.input.set(value)


class UiListChild(QFrame):
    def __init__(self, list, index):
        super().__init__()

        self.list = list
        self.index = index

        self.setFrameShape(QFrame.Shape.Panel)
        self.setFrameShadow(QFrame.Shadow.Raised)

        self.layout_manager = LayoutManager(self)

        with self.layout_manager.row() as row:
            with row.toolbar(orientation=Qt.Orientation.Vertical) as toolbar:
                with toolbar.tool_button(icon=Krita.icon("arrow-up"), tooltip="Move Up") as button:
                    self.move_up_button = button
                    button.clicked.connect(self.move_up)

                with toolbar.tool_button(icon=Krita.icon("arrow-down"), tooltip="Move Down") as button:
                    self.move_down_button = button
                    button.clicked.connect(self.move_down)

                toolbar.separator()

                with toolbar.tool_button(icon=Krita.icon("window-close"), tooltip="Delete") as button:
                    button.clicked.connect(self.remove)

            with row.column() as column:
                self.layout = column


    def update_buttons(self):
        self.move_up_button.setEnabled(self.index > 0)
        self.move_down_button.setEnabled(self.index < (len(self.list.children) - 1))


    def move_up(self):
        self.list.move_child_up(self.index)

    def move_down(self):
        self.list.move_child_down(self.index)


    def remove(self):
        reply = QMessageBox.question(
            self,
            "Delete",
            "Are you sure you want to delete?",
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.list.remove_child(self.index)


class UiList(QWidget):
    def __init__(self, input, trigger_refresh):
        super().__init__()

        self.input = input
        self.trigger_refresh = trigger_refresh

        self.children = []

        self.layout_manager = LayoutManager(self)

        with self.layout_manager.column() as column:
            self.layout = column


    def move_child_up(self, index):
        self.input.move(index, index - 1)
        self.trigger_refresh()

    def move_child_down(self, index):
        self.input.move(index, index + 1)
        self.trigger_refresh()

    def remove_child(self, index):
        self.input.remove(index)
        self.trigger_refresh()

    def add_child(self):
        self.input.add()
        self.trigger_refresh()


    def make_children(self):
        for index, workflow in enumerate(self.input.iter_children()):
            if index == 0:
                self.layout.spacer(2)
            else:
                self.layout.spacer(4)

            with self.layout.widget(UiListChild(self, index)) as child:
                self.children.append(child)
                yield (workflow, child.layout)

        for child in self.children:
            child.update_buttons()

        if len(self.children) > 0:
            self.layout.spacer(2)

        with self.layout.tool_button(icon=Krita.icon("addlayer"), text="Add...", tooltip="Add new item...") as button:
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.clicked.connect(self.add_child)

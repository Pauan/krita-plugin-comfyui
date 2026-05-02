import math
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QTextOption, QFontMetricsF
from PyQt6.QtWidgets import (
    QWidget,
    QFrame,
    QLineEdit,
    QPlainTextEdit,
    QCheckBox,
    QSlider,
    QMessageBox,
)
from ..util.qt import BlockSignals, LayoutManager, ComboBox
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


# @TODO don't hardcode the amount of steps
def step_size(minimum, maximum, step):
    return int(max(abs(maximum - minimum) / step, 1.0) * 1000000.0)

class UiFloat(QWidget):
    def __init__(self, input, slider, tooltip, min, max, step, decimals, multiplier, suffix):
        super().__init__()

        self.input = input
        self.min = min
        self.max = max
        self.decimals = decimals
        self.multiplier = multiplier

        if self.multiplier is None:
            self.multiplier = 1.0

        self.steps = step_size(min, max, step)

        self.setToolTip(self.input.format_tooltip(tooltip))

        self.layout_manager = LayoutManager(self)

        with self.layout_manager.row() as row:
            if slider:
                with row.slider() as widget:
                    widget.setOrientation(Qt.Orientation.Horizontal)
                    widget.setRange(0, self.steps)
                    widget.setSingleStep(1000000)
                    widget.setPageStep(1000000)
                    widget.setValue(self.value_to_slider(self.input.get()))
                    #widget.setTickInterval(1000000)
                    #widget.setTickPosition(QSlider.TickPosition.TicksAbove)
                    #widget.setMinimumHeight(self._slider.minimumSizeHint().height() + 4)
                    widget.valueChanged.connect(self.on_slider_changed)
                    self.slider_widget = widget

                row.spacer(4)

            else:
                self.slider_widget = None

            with row.float() as widget:
                if suffix is not None:
                    widget.setSuffix(suffix)

                widget.setRange(min * self.multiplier, max * self.multiplier)
                widget.setSingleStep(step * self.multiplier)
                widget.setDecimals(decimals)
                widget.setValue(self.input.get() * self.multiplier)
                widget.valueChanged.connect(self.on_value_changed)
                self.value_widget = widget


    def slider_to_value(self, value):
        if value == self.steps:
            return self.max
        elif value == 0:
            return self.min
        else:
            value = lerp(float(value) / float(self.steps), self.min, self.max)
            return round(value * self.multiplier, self.decimals) / self.multiplier


    def value_to_slider(self, value):
        if value == self.max:
            return self.steps
        elif value == self.min:
            return 0
        else:
            return int(normalize(value, self.min, self.max) * float(self.steps))


    def on_slider_changed(self, value):
        assert self.slider_widget is not None

        # Rounds to the nearest step
        new_value = round(float(value) / 1000000.0) * 1000000
        new_value = clamp(new_value, 0, self.steps)

        if value != new_value:
            value = new_value
            with BlockSignals(self.slider_widget):
                self.slider_widget.setValue(value)

        value = self.slider_to_value(value)
        value = clamp(value, self.min, self.max)

        with BlockSignals(self.value_widget):
            self.value_widget.setValue(value * self.multiplier)

        self.input.set(value)


    def on_value_changed(self, value):
        value = value / self.multiplier
        value = clamp(value, self.min, self.max)

        if self.slider_widget is not None:
            with BlockSignals(self.slider_widget):
                self.slider_widget.setValue(self.value_to_slider(value))

        self.input.set(value)


class UiInt(QWidget):
    def __init__(self, input, slider, tooltip, min, max, step, suffix):
        super().__init__()

        self.input = input
        self.min = min
        self.max = max
        self.step = step

        self.setToolTip(self.input.format_tooltip(tooltip))

        self.layout_manager = LayoutManager(self)

        with self.layout_manager.row() as row:
            if slider:
                with row.slider() as widget:
                    widget.setOrientation(Qt.Orientation.Horizontal)
                    widget.setRange(min, max)
                    widget.setSingleStep(step)
                    widget.setPageStep(step)
                    widget.setValue(self.input.get())
                    widget.valueChanged.connect(self.on_slider_changed)
                    self.slider_widget = widget

                row.spacer(4)

            else:
                self.slider_widget = None

            with row.int() as widget:
                if suffix is not None:
                    widget.setSuffix(suffix)

                widget.setRange(min, max)
                widget.setSingleStep(step)
                widget.setValue(self.input.get())
                widget.valueChanged.connect(self.on_value_changed)
                self.value_widget = widget


    def on_slider_changed(self, value):
        assert self.slider_widget is not None

        # Rounds to the nearest step
        new_value = round(float(value) / self.step) * self.step
        new_value = clamp(new_value, self.min, self.max)

        if value != new_value:
            value = new_value
            with BlockSignals(self.slider_widget):
                self.slider_widget.setValue(value)

        with BlockSignals(self.value_widget):
            self.value_widget.setValue(value)

        self.input.set(value)


    def on_value_changed(self, value):
        value = clamp(value, self.min, self.max)

        if self.slider_widget is not None:
            with BlockSignals(self.slider_widget):
                self.slider_widget.setValue(value)

        self.input.set(value)


class UiListChild(QFrame):
    def __init__(self, list, index, first_index, last_index):
        super().__init__()

        self.list = list
        self.index = index
        self.first_index = first_index
        self.last_index = last_index
        self.inputs = self.list.inputs.sub_inputs()

        self.setFrameShape(QFrame.Shape.Panel)
        self.setFrameShadow(QFrame.Shadow.Raised)

        self.layout_manager = LayoutManager(self)

        with self.layout_manager.row() as row:
            with row.toolbar(orientation=Qt.Orientation.Vertical) as toolbar:
                with toolbar.tool_button(icon=Krita.icon("arrow-up"), tooltip="Move Up") as button:
                    if self.index <= self.first_index:
                        button.setEnabled(False)
                    button.clicked.connect(self.move_up)

                with toolbar.tool_button(icon=Krita.icon("arrow-down"), tooltip="Move Down") as button:
                    if self.index >= (self.last_index - 1):
                        button.setEnabled(False)
                    button.clicked.connect(self.move_down)

                toolbar.separator()

                with toolbar.tool_button(icon=Krita.icon("window-close"), tooltip="Delete") as button:
                    button.clicked.connect(self.remove)

            with row.column() as column:
                self.layout = column


    def move_up(self):
        self.inputs.move_all_up()
        self.list.trigger_refresh()

    def move_down(self):
        self.inputs.move_all_down()
        self.list.trigger_refresh()


    def remove(self):
        reply = QMessageBox.question(
            self,
            "Delete",
            "Are you sure you want to delete?",
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.inputs.remove_all()
            self.list.subtract_length()
            self.list.trigger_refresh()


class UiList(QWidget):
    def __init__(self, input, inputs, start_index, trigger_refresh):
        super().__init__()

        self.input = input
        self.inputs = inputs
        self.start_index = start_index
        self.trigger_refresh = trigger_refresh

        self.layout_manager = LayoutManager(self)

        with self.layout_manager.column() as column:
            self.layout = column


    def length(self):
        return self.input.get()

    def add_length(self, amount=1):
        self.input.set(self.length() + amount)

    def subtract_length(self, amount=1):
        self.input.set(max(0, self.length() - amount))


    def add_child(self):
        self.add_length()
        self.trigger_refresh()


    def make_children(self):
        is_first = True

        first_index = self.start_index
        last_index = self.start_index + self.length()

        for index in range(first_index, last_index):
            if index == first_index:
                self.layout.spacer(2)
            else:
                self.layout.spacer(4)

            with self.layout.widget(UiListChild(self, index, first_index, last_index)) as child:
                yield (child.inputs, child.layout, index)

        if first_index != last_index:
            self.layout.spacer(2)

        with self.layout.tool_button(icon=Krita.icon("addlayer"), text="Add...", tooltip="Add new item...") as button:
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.clicked.connect(self.add_child)

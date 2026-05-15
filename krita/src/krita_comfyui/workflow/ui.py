from krita import SliderSpinBox, DoubleSliderSpinBox
import math
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QTextOption, QFontMetricsF
from PyQt6.QtWidgets import (
    QWidget,
    QFrame,
    QLineEdit,
    QPlainTextEdit,
    QMessageBox,
)
from ..util.qt import BlockSignals, LayoutManager, ComboBox, BooleanSwitch, BlockMouseWheel
from ..util import number_of_lines, lerp, normalize, clamp


class InputEqual:
    def __init__(self, input, value):
        self.input = input
        self.value = value


    @staticmethod
    def from_json(workflow, json, name):
        info = json.get(name, None)

        if info is not None:
            return InputEqual(
                workflow.input(info["id"]),
                info["value"],
            )

        return None


    def is_equal(self):
        return self.input.get() == self.value


    def when_equal(self, f):
        def on_change():
            f(self.is_equal())

        on_change()
        return self.input.add_listener(on_change)


class Inputs:
    def __init__(self, value, visible_if, enabled_if):
        super().__init__()
        self.value = value
        self.visible_if = visible_if
        self.enabled_if = enabled_if
        self.listeners = []


    def stop(self):
        for listener in self.listeners:
            listener.stop()


    def apply_to_widget(self, widget, tooltip):
        if self.visible_if is not None:
            self.listeners.append(self.visible_if.when_equal(Visibility(widget).set_visible))

        if self.enabled_if is not None:
            self.listeners.append(self.enabled_if.when_equal(widget.setEnabled))

        if self.value is not None:
            if tooltip is not None:
                widget.setToolTip(self.value.format_tooltip(tooltip))

            self.listeners.append(self.value.add_listener(widget.sync))


# If we call `widget.setVisible(True)` it will cause
# really bad flickering, so we use this class to avoid
# calling `widget.setVisible(True)` unless needed.
class Visibility:
    def __init__(self, widget):
        self.widget = widget
        self.is_visible = True

    def set_visible(self, visible):
        if self.is_visible != visible:
            self.is_visible = visible
            self.widget.setVisible(visible)


class UiCombo(ComboBox):
    def __init__(self, value, visible_if, enabled_if, tooltip, options):
        super().__init__()

        self.inputs = Inputs(value, visible_if, enabled_if)
        self.inputs.apply_to_widget(self, tooltip)

        self.activated.connect(self.on_changed)

        self.set_options(options)


    @staticmethod
    def from_json(workflow, json):
        return UiCombo(
            value=workflow.input(json["id"]),
            visible_if=InputEqual.from_json(workflow, json, "visible_if"),
            enabled_if=InputEqual.from_json(workflow, json, "enabled_if"),
            tooltip=json.get("tooltip", None),
            options=json.get("options", []),
        )


    def on_changed(self):
        selected = self.currentData()
        assert selected is not None
        assert isinstance(selected, str)
        self.inputs.value.set(selected)


    def sync(self):
        selected_value = self.inputs.value.get()

        if selected_value == "":
            index = 0
        else:
            index = self.findData(selected_value, flags=Qt.MatchFlag.MatchExactly)

        if index < 0:
            index = 0

        if self.currentIndex() != index:
            with BlockSignals(self):
                self.setCurrentIndex(index)


    def set_options(self, options):
        with BlockSignals(self):
            self.clear()

            self.addItem("", "")

            for option in options:
                if option.get("separator", False):
                    self.insertSeparator(self.count())
                    self.insertSeparator(self.count())

                elif option.get("icon", None) is not None:
                    self.addItem(Krita.icon(option["icon"]), option["label"], option["value"])

                else:
                    self.addItem(option["label"], option["value"])

            self.sync()
            self.resize_dropdown()


class UiBoolean(QWidget):
    def __init__(self, value, visible_if, enabled_if, tooltip, label, style):
        super().__init__()

        if style is None:
            style = "switch"

        self.inputs = Inputs(value, visible_if, enabled_if)
        self.inputs.apply_to_widget(self, tooltip=None)

        self.checkbox = BooleanSwitch(
            tooltip=self.inputs.value.format_tooltip(tooltip),
            label=label,
            style=style,
        )

        self.checkbox.changed.connect(self.on_changed)

        self.layout_manager = LayoutManager(self)

        with self.layout_manager.row() as row:
            row.widget(self.checkbox)
            row.stretch()

        self.sync()


    @staticmethod
    def from_json(workflow, json):
        return UiBoolean(
            value=workflow.input(json["id"]),
            visible_if=InputEqual.from_json(workflow, json, "visible_if"),
            enabled_if=InputEqual.from_json(workflow, json, "enabled_if"),
            tooltip=json.get("tooltip", None),
            label=json.get("label", None),
            style=json.get("style", None),
        )


    def sync(self):
        self.checkbox.setChecked(self.inputs.value.get())


    def on_changed(self):
        self.inputs.value.set(self.checkbox.isChecked())


class UiString(QLineEdit):
    def __init__(self, value, visible_if, enabled_if, placeholder, tooltip):
        super().__init__()

        self.inputs = Inputs(value, visible_if, enabled_if)
        self.inputs.apply_to_widget(self, tooltip)

        self.textEdited.connect(self.on_changed)

        if placeholder is not None:
            self.setPlaceholderText(placeholder)

        self.sync()


    @staticmethod
    def from_json(workflow, json):
        multiline = json.get("multiline", False)

        if multiline:
            return UiStringMultiline(
                value=workflow.input(json["id"]),
                visible_if=InputEqual.from_json(workflow, json, "visible_if"),
                enabled_if=InputEqual.from_json(workflow, json, "enabled_if"),
                tooltip=json.get("tooltip", None),
                placeholder=json.get("placeholder", None),
                background_color=json.get("background_color", None),
                min_lines=json.get("min_lines", None),
                max_lines=json.get("max_lines", None),
            )

        else:
            return UiString(
                value=workflow.input(json["id"]),
                visible_if=InputEqual.from_json(workflow, json, "visible_if"),
                enabled_if=InputEqual.from_json(workflow, json, "enabled_if"),
                tooltip=json.get("tooltip", None),
                placeholder=json.get("placeholder", None),
            )


    def sync(self):
        text = self.inputs.value.get()

        if text != self.text():
            with BlockSignals(self):
                self.setText(text)


    def on_changed(self):
        self.inputs.value.set(self.text())


class UiStringMultiline(QPlainTextEdit):
    def __init__(self, value, visible_if, enabled_if, background_color, placeholder, tooltip, min_lines, max_lines):
        super().__init__()

        if min_lines is None:
            min_lines = 2

        if max_lines is None:
            max_lines = 6

        self.inputs = Inputs(value, visible_if, enabled_if)
        self.inputs.apply_to_widget(self, tooltip)

        self.min_lines = min_lines
        self.max_lines = max_lines

        self.textChanged.connect(self.on_changed)

        self.setTabChangesFocus(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.setFrameStyle(QFrame.Shape.StyledPanel)

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

        if placeholder is not None:
            self.setPlaceholderText(placeholder)

        self.sync()


    def sync(self):
        text = self.inputs.value.get()

        self.resize(text)

        if text != self.toPlainText():
            with BlockSignals(self):
                self.setPlainText(text)


    def get_pixel_height(self, lines):
        metrics = QFontMetricsF(self.document().defaultFont())
        return math.ceil(metrics.lineSpacing() * (lines + 1))


    def resize(self, text):
        lines = max(self.min_lines, min(number_of_lines(text) + 1, self.max_lines))
        self.setFixedHeight(self.get_pixel_height(lines))


    def on_changed(self):
        self.inputs.value.set(self.toPlainText())


    def wheelEvent(self, event):
        super().wheelEvent(event)

        scrollbar = self.verticalScrollBar()

        # If we have a vertical scrollbar, then this prevents the mouse wheel
        # from scrolling the parent, now it will only scroll the text box.
        if scrollbar is not None and scrollbar.isVisible():
            event.accept()


class UiGroup(QWidget):
    def __init__(self, value, visible_if, enabled_if, title, indent):
        super().__init__()

        if title is None:
            title = ""

        if indent is None:
            indent = False

        self.inputs = Inputs(value, visible_if, enabled_if)
        self.inputs.apply_to_widget(self, tooltip=None)

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
                button.setText(title)
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                button.toggled.connect(self.on_toggled)
                self.toggle_button = button

            with column.widget(QWidget()) as widget:
                layout = LayoutManager(widget)
                self.container = widget

                with layout.column() as column:
                    if indent:
                        # TODO figure out a way to calculate this automatically
                        column.set_padding(top=3, left=20)
                    else:
                        column.set_padding(top=3)
                    self.layout = column

        self.sync()


    @staticmethod
    def from_json(workflow, json):
        return UiGroup(
            value=workflow.input(json["id"]),
            visible_if=InputEqual.from_json(workflow, json, "visible_if"),
            enabled_if=InputEqual.from_json(workflow, json, "enabled_if"),
            title=json.get("title", None),
            indent=json.get("indent", None),
        )


    def sync(self):
        checked = self.inputs.value.get()

        with BlockSignals(self.toggle_button):
            self.toggle_button.setChecked(checked)

        if checked:
            self.toggle_button.setArrowType(Qt.ArrowType.DownArrow)
            self.toggle_button.setToolTip("Close group...")
            self.container.show()

        else:
            self.toggle_button.setArrowType(Qt.ArrowType.RightArrow)
            self.toggle_button.setToolTip("Open group...")
            self.container.hide()


    def on_toggled(self, checked):
        if self.inputs.value.default == checked:
            self.inputs.value.reset_to_default()
        else:
            self.inputs.value.set(checked)


class UiRow(QWidget):
    def __init__(self, visible_if):
        super().__init__()

        self.inputs = Inputs(value=None, visible_if=visible_if, enabled_if=None)
        self.inputs.apply_to_widget(self, tooltip=None)

        self.layout_manager = LayoutManager(self)

        with self.layout_manager.row() as row:
            self.layout = row


    @staticmethod
    def from_json(workflow, json):
        return UiRow(
            visible_if=InputEqual.from_json(workflow, json, "visible_if"),
        )


class UiFloat(QWidget):
    def __init__(self, value, visible_if, enabled_if, slider, tooltip, min, max, step, decimals, multiplier, prefix, suffix):
        super().__init__()

        # 53-bit signed integer, the maximum safe integer with a 64-bit float
        if min is None:
            min = -9007199254740991.0
        if max is None:
            max = 9007199254740991.0

        if step is None:
            step = 0.01

        if multiplier is None:
            multiplier = 1.0

        if decimals is None:
            decimals = 2

        if slider is None:
            slider = False

        self.inputs = Inputs(value, visible_if, enabled_if)
        self.inputs.apply_to_widget(self, tooltip)

        self.min = min
        self.max = max
        self.step = step
        self.decimals = decimals
        self.multiplier = multiplier

        self.layout_manager = LayoutManager(self)

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
                    widget.valueChanged.connect(self.on_value_changed)
                    self.value_widget = widget

        self.sync()


    @staticmethod
    def from_json(workflow, json):
        return UiFloat(
            value=workflow.input(json["id"]),
            visible_if=InputEqual.from_json(workflow, json, "visible_if"),
            enabled_if=InputEqual.from_json(workflow, json, "enabled_if"),
            tooltip=json.get("tooltip", None),
            slider=json.get("slider", None),
            min=json.get("min", None),
            max=json.get("max", None),
            step=json.get("step", None),
            multiplier=json.get("multiplier", None),
            prefix=json.get("prefix", None),
            suffix=json.get("suffix", None),
            decimals=json.get("decimals", None),
        )


    @staticmethod
    def from_json_percentage(workflow, json):
        return UiFloat(
            value=workflow.input(json["id"]),
            visible_if=InputEqual.from_json(workflow, json, "visible_if"),
            enabled_if=InputEqual.from_json(workflow, json, "enabled_if"),
            tooltip=json.get("tooltip", None),
            slider=json.get("slider", True),
            min=0.0,
            max=1.0,
            step=json.get("step", None),
            multiplier=100.0,
            prefix=json.get("prefix", None),
            suffix="%",
            decimals=0,
        )


    def sync(self):
        with BlockSignals(self.value_widget):
            display_value = round(clamp(self.inputs.value.get(), self.min, self.max) * self.multiplier, self.decimals)
            self.value_widget.setValue(display_value)


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

        self.inputs.value.set(value)


class UiInt(QWidget):
    def __init__(self, value, visible_if, enabled_if, slider, tooltip, min, max, step, prefix, suffix):
        super().__init__()

        # 32-bit signed integer
        if min is None:
            min = -2147483648
        if max is None:
            max = 2147483647

        if step is None:
            step = 1

        if slider is None:
            slider = False

        self.inputs = Inputs(value, visible_if, enabled_if)
        self.inputs.apply_to_widget(self, tooltip)

        self.min = min
        self.max = max
        self.step = step

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
                    widget.valueChanged.connect(self.on_value_changed)
                    self.value_widget = widget

        self.sync()


    @staticmethod
    def from_json(workflow, json):
        return UiInt(
            value=workflow.input(json["id"]),
            visible_if=InputEqual.from_json(workflow, json, "visible_if"),
            enabled_if=InputEqual.from_json(workflow, json, "enabled_if"),
            tooltip=json.get("tooltip", None),
            slider=json.get("slider", None),
            min=json.get("min", None),
            max=json.get("max", None),
            step=json.get("step", None),
            prefix=json.get("prefix", None),
            suffix=json.get("suffix", None),
        )


    def sync(self):
        with BlockSignals(self.value_widget):
            self.value_widget.setValue(clamp(self.inputs.value.get(), self.min, self.max))


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

        self.inputs.value.set(value)


class UiListChild(QFrame):
    def __init__(self, list, index):
        super().__init__()

        self.list = list
        self.index = index

        self.setContentsMargins(0, 0, 0, 0)

        self.setFrameShape(QFrame.Shape.Panel)
        self.setFrameShadow(QFrame.Shadow.Raised)

        self.layout_manager = LayoutManager(self)

        with self.layout_manager.row() as row:
            row.set_padding(right=1)

            with row.column(align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop) as column:
                with column.toolbar(orientation=Qt.Orientation.Vertical) as toolbar:
                    with toolbar.tool_button(icon=Krita.icon("arrow-up"), tooltip="Move Up") as button:
                        self.move_up_button = button
                        button.clicked.connect(self.move_up)

                    with toolbar.tool_button(icon=Krita.icon("arrow-down"), tooltip="Move Down") as button:
                        self.move_down_button = button
                        button.clicked.connect(self.move_down)

                    toolbar.separator()

                    with toolbar.tool_button(icon=Krita.icon("window-close"), tooltip="Delete") as button:
                        button.clicked.connect(self.remove)

            with row.column(stretch=1, align=Qt.AlignmentFlag.AlignTop) as column:
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


# TODO it should sync when the input changes
class UiList(QWidget):
    def __init__(self, input, visible_if, enabled_if, label, trigger_refresh):
        super().__init__()

        self.inputs = Inputs(value=None, visible_if=visible_if, enabled_if=enabled_if)
        self.inputs.apply_to_widget(self, tooltip=None)

        self.input = input
        self.label = label
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
                self.layout.spacer(3)

            with self.layout.widget(UiListChild(self, index)) as child:
                self.children.append(child)
                yield (workflow, child.layout)

        for child in self.children:
            child.update_buttons()

        if len(self.children) > 0:
            self.layout.spacer(2)

        if self.label is None:
            text = "Add"
            tooltip = "Add new item."
        else:
            text = f"Add {self.label}"
            tooltip = f"Add new {self.label}."

        with self.layout.tool_button(icon=Krita.icon("addlayer"), text=text, tooltip=tooltip) as button:
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.clicked.connect(self.add_child)

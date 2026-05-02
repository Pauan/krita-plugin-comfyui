from krita import DockWidget
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QMessageBox,
    QSizePolicy,
    QWidget,
)
from ..util import number_of_decimals
from ..util.krita import DocumentManager
from ..util.qt import LayoutManager, MessageBox, ComboBox, BlockSignals

from . import Workflow
from .graph import WorkflowError
from .ui import UiLayerId, UiCombo, UiInt, UiFloat, UiString, UiStringMultiline, UiGroup, UiRow, UiList


class WorkflowSelector(ComboBox):
    def __init__(self, tooltip):
        super().__init__()
        self.setToolTip(tooltip)


    def set_values(self, values):
        with BlockSignals(self):
            self.clear()

            self.addItem("", "")

            for workflow in values:
                self.addItem(Krita.icon(workflow["icon"]), workflow["name"], workflow["id"])

            self.resize_dropdown()


    def set_selected(self, id):
        with BlockSignals(self):
            if id == "":
                index = 0
            else:
                index = self.findData(id, flags=Qt.MatchFlag.MatchExactly)

            if self.currentIndex() != index:
                self.setCurrentIndex(index)


class WorkflowWidget(QWidget):
    can_run_changed = pyqtSignal()

    def __init__(self, extension):
        super().__init__()

        self.extension = extension
        self.extension.settings.node_metadata_changed.connect(self.on_metadata_changed)

        self.document = DocumentManager(self)
        self.document.document_changed.connect(self.on_document_changed)
        self.document.layers_changed.connect(self.update_layer_inputs)

        self.layout = LayoutManager(self)

        self.workflow = Workflow(self.extension.settings)
        self.workflow.setParent(self)
        self.workflow.change_document(self.document.current())

        self.error = MessageBox(QMessageBox.Icon.Critical, "Workflow error", "", parent=self)
        self.error.setSizeGripEnabled(True)
        self.error.setTextFormat(Qt.TextFormat.PlainText)

        self.layer_inputs = []

        with self.layout.column() as column:
            with column.row() as row:
                row.set_padding(left=2, right=2, bottom=4)

                with row.widget(WorkflowSelector(tooltip="Workflow")) as combo:
                    self.workflow_selector = combo

                    combo.activated.connect(self.on_workflow_changed)

                    combo.set_values(self.extension.settings.load_all_workflows())
                    combo.set_selected(self.workflow.id)

                with row.tool_button(icon=Krita.icon("properties"), tooltip="Open settings") as button:
                    button.clicked.connect(self.open_settings)

            with column.scroll() as scroll:
                widget = QWidget()
                layout = LayoutManager(widget)

                # Causes the children to shrink horizontally, to avoid a horizontal scrollbar
                widget.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred))

                with layout.column() as column:
                    column.set_padding(left=2, right=2)
                    self.widgets = column

                scroll.setWidget(widget)

        self.update_widgets()


    # If the widget has a link_to, we need to fetch the
    # node metadata and merge it into the widget info.
    def get_node_metadata(self, info):
        link_to = info.get("link_to", None)

        if link_to is None:
            return info

        else:
            new_info = {}

            metadata = self.extension.settings.get_node_metadata(link_to["node_id"]).input(link_to["input"])

            # Combo values
            try:
                new_info["values"] = metadata.info["options"]
            except KeyError:
                pass

            # decimals
            try:
                decimals = number_of_decimals(metadata.info["round"], None)
                if decimals is not None:
                    new_info["decimals"] = decimals
            except KeyError:
                pass

            # Copy metadata over as-is
            for name in ("min", "max", "step", "tooltip", "multiline", "placeholder"):
                try:
                    new_info[name] = metadata.info[name]
                except KeyError:
                    pass

            # Widget info always overrides node metadata
            for key, value in info.items():
                new_info[key] = value

            return new_info


    def add_widget(self, inputs, parent, info, index):
        info = self.get_node_metadata(info)

        match info["type"]:
            case "layer_id":
                widget = UiLayerId(
                    inputs.input(info["id"], index),
                    tooltip=info.get("tooltip", None),
                    layers=self.document.layers,
                )

                self.layer_inputs.append(widget)

                parent.widget(widget)


            case "combo":
                parent.widget(UiCombo(
                    inputs.input(info["id"], index),
                    tooltip=info.get("tooltip", None),
                    values=info.get("values", []),
                ))


            case "string":
                multiline = info.get("multiline", False)

                if multiline:
                    widget = UiStringMultiline(
                        inputs.input(info["id"], index),
                        tooltip=info.get("tooltip", None),
                        placeholder=info.get("placeholder", None),
                        background_color=info.get("background_color", None),
                        min_lines=info.get("min_lines", 2),
                        max_lines=info.get("max_lines", 6),
                    )

                else:
                    widget = UiString(
                        inputs.input(info["id"], index),
                        tooltip=info.get("tooltip", None),
                        placeholder=info.get("placeholder", None),
                    )

                parent.widget(widget)


            case "int":
                parent.widget(UiInt(
                    inputs.input(info["id"], index),
                    tooltip=info.get("tooltip", None),
                    slider=info.get("slider", False),
                    # 32-bit signed integer
                    min=info.get("min", -2147483648),
                    max=info.get("max", 2147483647),
                    step=info.get("step", 1),
                    suffix=info.get("suffix", None),
                ))


            case "float":
                parent.widget(widget = UiFloat(
                    inputs.input(info["id"], index),
                    tooltip=info.get("tooltip", None),
                    slider=info.get("slider", False),
                    min=info.get("min", 0.0),
                    max=info.get("max", 1.0),
                    step=info.get("step", 0.01),
                    multiplier=info.get("multiplier", None),
                    suffix=info.get("suffix", None),
                    decimals=info.get("decimals", 2),
                ))


            case "percentage":
                parent.widget(UiFloat(
                    inputs.input(info["id"], index),
                    tooltip=info.get("tooltip", None),
                    slider=info.get("slider", True),
                    min=0.0,
                    max=1.0,
                    step=info.get("step", 0.01),
                    multiplier=100.0,
                    suffix="%",
                    decimals=info.get("decimals", 0),
                ))


            case "group":
                widget = UiGroup(
                    inputs.input(info["id"], index),
                    title=info.get("title", ""),
                )

                for child in info["children"]:
                    self.add_widget(inputs, widget.layout, child, index)

                parent.widget(widget)


            case "row":
                widget = UiRow()

                for child in info["children"]:
                    self.add_widget(inputs, widget.layout, child, index)

                parent.widget(widget)


            case "list":
                widget = UiList(
                    inputs.input(info["id"], index),
                    inputs=inputs,
                    start_index=index,

                    # When an item is added, removed, or moved, it clears out all the
                    # existing widgets and remakes them from scratch.
                    #
                    # This is a performance cost, but it guarantees that the internal
                    # state will always be correct.
                    trigger_refresh=self.update_widgets,
                )

                for (inputs, layout, index) in widget.make_children():
                    for child in info["children"]:
                        self.add_widget(inputs, layout, child, index)

                parent.widget(widget)

            case _:
                raise RuntimeError(f"Unknown widget type {info["type"]}")


    def update_widgets(self):
        self.widgets.clear()
        self.layer_inputs = []

        if self.workflow.layout is not None:
            for widget in self.workflow.layout:
                self.add_widget(self.workflow, self.widgets, widget, 0)

        self.widgets.stretch()


    def update_layer_inputs(self):
        print("Updating layers")

        layers = self.document.layers

        for input in self.layer_inputs:
            input.set_layers(layers)


    def on_metadata_changed(self):
        if self.workflow.change_metadata():
            # Various `link_to` stuff might have changed, so we have to remake all of the widgets.
            self.update_widgets()


    def on_workflow_changed(self):
        if self.workflow.change_workflow(self.workflow_selector.currentData()):
            self.update_widgets()
            self.can_run_changed.emit()


    def on_document_changed(self):
        if self.workflow.change_document(self.document.current()):
            self.update_widgets()
            self.workflow_selector.set_selected(self.workflow.id)
            self.can_run_changed.emit()


    def can_run(self):
        return self.workflow.is_valid()


    def show_error(self, message, backtrace=None):
        self.error.setText(message)

        if backtrace is None:
            self.error.setDetailedText("")
        else:
            self.error.setDetailedText(backtrace)

        self.error.exec()


    def run_workflow(self):
        try:
            graph = self.workflow.to_graph()

        except WorkflowError as e:
            self.show_error(message=str(e))
            return

        self.extension.client.execute_graph(graph)


    def open_settings(self):
        self.extension.show_settings()

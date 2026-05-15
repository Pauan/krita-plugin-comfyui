from krita import DockWidget
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QMessageBox,
    QSizePolicy,
    QWidget,
    QFrame,
)
from ..util import number_of_decimals
from ..util.krita import DocumentManager
from ..util.qt import LayoutManager, MessageBox, ComboBox, BlockSignals

from . import Workflow
from .graph import WorkflowError
from .ui import InputEqual, UiCombo, UiInt, UiFloat, UiBoolean, UiString, UiStringMultiline, UiGroup, UiRow, UiList


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
        self.extension.settings.workflows.changed.connect(self.on_workflows_changed)

        self.document = DocumentManager(self)
        self.document.document_changed.connect(self.on_document_changed)
        self.document.layers_changed.connect(self.update_layer_inputs)

        self.layout = LayoutManager(self)

        self.workflow = Workflow(self.extension.settings)

        self.error = MessageBox(QMessageBox.Icon.Critical, "Workflow error", "", parent=self)
        self.error.setSizeGripEnabled(True)
        self.error.setTextFormat(Qt.TextFormat.PlainText)

        self.layer_combo_options = self.get_layer_combo_options()
        self.ui_widgets = []
        self.ui_layer_inputs = []

        with self.layout.column() as column:
            with column.row() as row:
                row.set_padding(left=1, right=1, bottom=2)

                with row.widget(WorkflowSelector(tooltip="Workflow")) as combo:
                    self.workflow_selector = combo
                    combo.activated.connect(self.on_workflow_changed)

                with row.tool_button(icon=Krita.icon("properties"), tooltip="Open settings") as button:
                    button.clicked.connect(self.open_settings)

            with column.scroll() as scroll:
                scroll.setFrameShape(QFrame.Shape.Panel)
                scroll.setFrameShadow(QFrame.Shadow.Sunken)

                widget = QWidget()
                layout = LayoutManager(widget)

                # Causes the children to shrink horizontally, to avoid a horizontal scrollbar
                widget.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred))

                with layout.column() as column:
                    column.set_padding(left=2, right=2, top=3)

                    with column.column(align=Qt.AlignmentFlag.AlignTop) as widgets:
                        self.widgets_container = widgets

                    column.stretch()

                scroll.setWidget(widget)

        self.update_workflow_selector()

        if self.workflow.change_document(self.document.current()):
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
                new_info["options"] = [{ "label": option, "value": option } for option in metadata.info["options"]]
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


    def add_widget(self, storage, parent, info, default_stretch):
        info = self.get_node_metadata(info)

        match info["type"]:
            case "layer_id":
                widget = UiCombo(
                    value=storage.item(info["id"]),
                    visible_if=InputEqual.from_json(storage, info, "visible_if"),
                    enabled_if=InputEqual.from_json(storage, info, "enabled_if"),
                    tooltip=info.get("tooltip", None),
                    options=self.layer_combo_options,
                )

                self.ui_widgets.append(widget)
                self.ui_layer_inputs.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "combo":
                widget = UiCombo.from_json(storage, info)
                self.ui_widgets.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "string":
                widget = UiString.from_json(storage, info)
                self.ui_widgets.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "boolean":
                widget = UiBoolean.from_json(storage, info)
                self.ui_widgets.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "int":
                widget = UiInt.from_json(storage, info)
                self.ui_widgets.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "float":
                widget = UiFloat.from_json(storage, info)
                self.ui_widgets.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "percentage":
                widget = UiFloat.from_json_percentage(storage, info)
                self.ui_widgets.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "group":
                widget = UiGroup.from_json(storage, info)

                for child in info["children"]:
                    self.add_widget(storage, widget.layout, child, default_stretch)

                self.ui_widgets.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "row":
                assert not "enabled_if" in info

                widget = UiRow.from_json(storage, info)

                for child in info["children"]:
                    self.add_widget(storage, widget.layout, child, default_stretch)

                self.ui_widgets.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "list":
                widget = UiList(
                    values=storage.item_list(info["id"]),
                    label=info.get("label", None),

                    visible_if=InputEqual.from_json(storage, info, "visible_if"),
                    enabled_if=InputEqual.from_json(storage, info, "enabled_if"),

                    # When an item is added, removed, or moved, it clears out all the
                    # existing widgets and remakes them from scratch.
                    #
                    # This is a performance cost, but it guarantees that the internal
                    # state will always be correct.
                    trigger_refresh=self.update_widgets,
                )

                for storage, layout in widget.make_children():
                    for child in info["children"]:
                        self.add_widget(storage, layout, child, default_stretch)

                self.ui_widgets.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))

            case _:
                raise RuntimeError(f"Unknown widget type {info["type"]}")


    def update_workflow_selector(self):
        self.workflow_selector.set_values(self.extension.settings.get_all_workflows())
        self.workflow_selector.set_selected(self.workflow.id)


    def update_widgets(self):
        # Cleanup the old widgets.
        for widget in self.ui_widgets:
            widget.inputs.stop()

        self.ui_widgets = []
        self.ui_layer_inputs = []

        self.widgets_container.clear()

        if self.workflow.layout is not None:
            for widget in self.workflow.layout:
                self.add_widget(self.workflow, self.widgets_container, widget, 0)


    def get_layer_combo_options(self):
        options = []

        for layer in self.document.layers:
            if layer is None:
                options.append({ "separator": True })
            else:
                options.append({
                    "icon": layer.type.icon_name(),
                    "label": layer.name,
                    "value": layer.id,
                })

        return options


    def update_layer_inputs(self):
        self.layer_combo_options = self.get_layer_combo_options()

        for input in self.ui_layer_inputs:
            input.set_options(self.layer_combo_options)


    def on_workflows_changed(self):
        if self.workflow.reload_workflow():
            self.update_widgets()

        self.update_workflow_selector()


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
            self.layer_combo_options = self.get_layer_combo_options()
            self.update_widgets()
            self.workflow_selector.set_selected(self.workflow.id)
            self.can_run_changed.emit()
        else:
            self.update_layer_inputs()


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
        defaults = self.workflow.get_defaults()
        ui_values = {}

        for id in defaults.keys():
            ui_values[id] = []

        # Collects all of the UI inputs and puts their values into a flat array, organized by ID.
        for widget in self.ui_widgets:
            inputs = widget.inputs

            input = inputs.value

            if input is not None:
                # TODO maybe do this for enabled_if too ?
                if inputs.visible_if is None or inputs.visible_if.is_equal():
                    ui_values[input.id].append(input.value)

        try:
            graph = self.workflow.to_graph(ui_values, defaults)

        except WorkflowError as e:
            self.show_error(message=str(e))
            return

        self.extension.client.execute_graph(graph)


    def open_settings(self):
        self.extension.show_settings()

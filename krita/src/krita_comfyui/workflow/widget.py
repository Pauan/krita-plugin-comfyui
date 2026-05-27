import time
import traceback
import contextlib
from krita import DockWidget
from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QMessageBox,
    QSizePolicy,
    QWidget,
    QFrame,
)
from ..shared import Perf
from ..util import number_of_decimals
from ..util.krita import DocumentManager
from ..util.qt import LayoutManager, MessageBox, ComboBox, BlockSignals

from . import Workflow
from .ui import InputEqual, UiCombo, UiLayerId, UiInt, UiFloat, UiBoolean, UiString, UiPrompt, UiGroup, UiRow, UiList, UiLabel
from .prompt import PromptParser
from .graph import WorkflowGraph


class WorkflowSelector(ComboBox):
    def __init__(self, tooltip):
        super().__init__()
        self.setToolTip(tooltip)


    def set_values(self, values):
        with BlockSignals(self):
            self.clear()

            self.addItem("", "")

            for workflow in values:
                if not workflow.is_hidden():
                    self.addItem(Krita.icon(workflow.icon()), workflow.name(), workflow.id())

            self.resize_dropdown()


    def set_selected(self, id):
        with BlockSignals(self):
            if id == "":
                index = 0
            else:
                index = self.findData(id, flags=Qt.MatchFlag.MatchExactly)

            if self.currentIndex() != index:
                self.setCurrentIndex(index)


class LiveModeState(QObject):
    # When running live mode we poll for changes every 100 ms.
    POLL_DELAY = 100

    # When a change happens we wait this many milliseconds before
    # we run the workflow.
    DEBOUNCE_DELAY = 150 * 1000000


    def __init__(self, parent, extension):
        super().__init__(parent)

        self.live_mode_enabled = extension.settings.settings.item("live_mode_enabled")
        self.fixed_seed_enabled = extension.settings.settings.item("fixed_seed_enabled")
        self.fixed_seed = extension.settings.settings.item("fixed_seed")

        self.is_running = False
        self.debounce_time = None

        self.timer = QTimer(self)
        self.timer.setSingleShot(False)
        self.timer.setInterval(self.POLL_DELAY)


    def stop(self):
        if self.is_running:
            self.is_running = False
            self.debounce_time = None
            self.timer.stop()
            return True

        return False


    def start(self):
        if not self.is_running:
            assert not self.timer.isActive()
            assert self.debounce_time is None
            self.is_running = True
            return True

        return False


    def set_debounce_time(self, document, now):
        document.modified = False

        self.debounce_time = now + self.DEBOUNCE_DELAY

        # We're running the workflow, so we don't need the timer.
        self.timer.stop()


    def check_changed(self, document, *, force_modified=False):
        if not self.is_running:
            return False

        if document is None:
            return False

        now = time.monotonic_ns()

        # Run the workflow immediately.
        if self.debounce_time is None:
            self.set_debounce_time(document, now)
            return True

        # Only run the workflow if the document changed and enough time has passed.
        if (force_modified or document.modified) and now >= self.debounce_time:
            self.set_debounce_time(document, now)
            return True

        # We couldn't run, so poll until something changes.
        if not self.timer.isActive():
            self.timer.start()

        return False


class WorkflowWidget(QWidget):
    can_run_changed = pyqtSignal()
    live_mode_changed = pyqtSignal()

    def __init__(self, extension):
        super().__init__()

        self.extension = extension
        self.extension.stop_live_mode.connect(self.stop_live_mode)
        self.extension.settings.node_metadata_changed.connect(self.on_metadata_changed)
        self.extension.settings.workflows.changed.connect(self.on_workflows_changed)

        self.document = DocumentManager(self)
        self.document.document_changed.connect(self.on_document_changed)
        self.document.layers_changed.connect(self.update_layer_inputs)

        self.live_mode_state = LiveModeState(self, self.extension)
        # TODO cleanup listeners when dock is removed
        self.live_mode_state.live_mode_enabled.add_listener(self.on_live_mode_changed)
        self.live_mode_state.fixed_seed_enabled.add_listener(self.on_seed_changed)
        self.live_mode_state.fixed_seed.add_listener(self.on_seed_changed)
        self.live_mode_state.timer.timeout.connect(self.maybe_run_live_mode)

        self.prompt_parser = PromptParser(self.extension.settings.bundles)

        self.layout = LayoutManager(self)

        self.workflow = Workflow(self.extension)

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

        with self.catch_errors():
            if self.workflow.change_document(self.document.current()):
                self.update_widgets()


    def open_settings(self):
        self.extension.show_settings()


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
                widget = UiLayerId.from_json(storage, info, self.layer_combo_options)
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


            case "prompt":
                widget = UiPrompt.from_json(storage, info, self.extension.settings)
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


            case "label":
                assert not "enabled_if" in info
                widget = UiLabel.from_json(storage, info)
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
        self.workflow_selector.set_values(self.extension.settings.workflows.get_all())
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
                    "label": layer.path,
                    "value": layer.id,
                    "layer_name": layer.name,
                })

        return options


    def update_layer_inputs(self):
        self.layer_combo_options = self.get_layer_combo_options()

        for input in self.ui_layer_inputs:
            input.set_options(self.layer_combo_options)


    def on_workflows_changed(self):
        with self.catch_errors():
            if self.workflow.reload_workflow():
                self.update_widgets()

            self.update_workflow_selector()


    def on_metadata_changed(self):
        with self.catch_errors():
            if self.workflow.change_metadata():
                # Various `link_to` stuff might have changed, so we have to remake all of the widgets.
                self.update_widgets()


    def on_workflow_changed(self):
        with self.catch_errors():
            if self.workflow.change_workflow(self.workflow_selector.currentData()):
                self.update_widgets()
                self.can_run_changed.emit()


    def on_document_changed(self):
        with self.catch_errors():
            self.stop_live_mode()

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
        self.stop_live_mode()

        self.error.setText(message)

        if backtrace is None:
            self.error.setDetailedText("")
        else:
            self.error.setDetailedText(backtrace)

        self.error.exec()


    @contextlib.contextmanager
    def catch_errors(self):
        try:
            yield
        except Exception as e:
            self.show_error(message=str(e), backtrace="".join(traceback.format_exception(e)))


    def get_ui_values(self):
        ui_values = {}

        for id in self.workflow.layout_ids:
            ui_values[id] = []

        # Collects all of the UI inputs and puts their values into a flat array, organized by ID.
        for widget in self.ui_widgets:
            inputs = widget.inputs

            input = inputs.value

            if input is not None:
                is_visible = inputs.visible_if is None or inputs.visible_if.is_equal()
                is_enabled = inputs.enabled_if is None or inputs.enabled_if.is_equal()

                if is_visible and is_enabled:
                    info = {
                        "value": input.value,
                        "is_default": input.value == input.default,
                    }

                    if isinstance(widget, UiPrompt):
                        parsed = self.prompt_parser.parse(input.value)
                        info["positive"] = parsed.serialize_positive()
                        info["negative"] = parsed.serialize_negative()
                        info["loras"] = parsed.loras

                    elif isinstance(widget, UiLayerId):
                        info["layer_name"] = ""

                        option = widget.current_option()

                        if option is not None:
                            try:
                                info["layer_name"] = option["layer_name"]
                            except KeyError:
                                pass

                    elif isinstance(widget, UiCombo):
                        info["label"] = ""

                        option = widget.current_option()

                        if option is not None:
                            info["label"] = option["label"]
                            assert info["label"] == widget.currentText()

                    ui_values[input.id].append(info)

        return ui_values


    def get_seed(self):
        if self.extension.settings.settings.get("fixed_seed_enabled"):
            return self.extension.settings.settings.get("fixed_seed")
        else:
            return WorkflowGraph.random_seed()


    def run_workflow(self):
        with Perf("run_workflow"):
            self.workflow.run_graph(
                ui_values=self.get_ui_values(),
                seed=self.get_seed(),
                is_live_mode=False,
                should_notify=True,
            )


    def run_live_workflow(self):
        with Perf("run_live_workflow"):
            self.workflow.run_graph(
                ui_values=self.get_ui_values(),
                seed=self.get_seed(),
                is_live_mode=True,
                should_notify=False,
            )

            assert not self.workflow.document.modified


    def is_live_mode_enabled(self):
        return self.live_mode_state.live_mode_enabled.get()

    def is_live_mode_running(self):
        return self.live_mode_state.is_running


    def on_live_mode_changed(self, old, new):
        if not new:
            self.stop_live_mode(emit=False)

        self.live_mode_changed.emit()


    def on_seed_changed(self, old, new):
        self.maybe_run_live_mode(force_modified=True)


    def stop_live_mode(self, *, emit=True):
        if self.live_mode_state.stop():
            self.extension.client.clear_queue_live_mode()

            # TODO more robust way to handle this
            if self.workflow.document is not None:
                self.workflow.document.modified = True

            if emit:
                self.live_mode_changed.emit()


    def maybe_run_live_mode(self, *, force_modified=False):
        is_changed = self.live_mode_state.check_changed(self.workflow.document, force_modified=force_modified)

        if is_changed:
            self.run_live_workflow()


    def toggle_live_mode_running(self):
        if self.is_live_mode_running():
            self.stop_live_mode()
        else:
            if self.live_mode_state.start():
                self.extension.live_mode_started.emit()
                self.maybe_run_live_mode()
                self.live_mode_changed.emit()

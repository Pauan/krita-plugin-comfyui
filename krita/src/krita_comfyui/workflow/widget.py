import time
import contextlib
from krita import DockWidget
from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QSizePolicy,
    QWidget,
    QFrame,
    QToolButton,
    QAbstractScrollArea,
)
from shared import Perf
from ..util import number_of_decimals
from ..util.krita import DocumentManager
from ..util.qt import LayoutManager, MessageBox, ComboBox, Menu, ScrollArea, BlockSignals

from . import Workflow
from .ui import InputEqual, UiCombo, UiLayerId, UiInt, UiFloat, UiBoolean, UiString, UiPrompt, UiGroup, UiRow, UiList, UiLabel, UiSeed
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


class WorkflowSettings(QWidget):
    def __init__(self, extension, settings):
        super().__init__()

        self.extension = extension
        self.settings = settings

        self.layout_manager = LayoutManager(self)

        self.setMaximumWidth(400)
        self.setMaximumHeight(600)

        with self.layout_manager.column() as root:
            with root.row() as top:
                top.set_padding(left=6, top=6, right=6, bottom=6)

                top.widget(UiBoolean(
                    value=self.settings.with_selected_workflow(lambda x: x.value("live_mode_enabled", bool)),
                    is_default=False,
                    reset_to_default=True,
                    visible_if=[],
                    enabled_if=[],
                    tooltip="Enable live mode, which automatically generates new images.",
                    label="Enable live mode.",
                    style="switch",
                ))

                top.stretch()

                top.spacer(16)

                with top.tool_button(icon=Krita.icon("configure-thicker"), tooltip="Open settings") as button:
                    button.clicked.connect(self.extension.show_settings)


            with root.widget(ScrollArea()) as scroll:
                self.scroll = scroll

                scroll.setFrameShape(QFrame.Shape.Panel)
                scroll.setFrameShadow(QFrame.Shadow.Sunken)

                # Needed to get the right size
                scroll.setWidgetResizable(True)
                scroll.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
                scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

                self.scroll_widget = QWidget()
                self.scroll_layout = LayoutManager(self.scroll_widget)

                # Causes the children to shrink horizontally, to avoid a horizontal scrollbar
                self.scroll_widget.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred))

                with self.scroll_layout.column() as column:
                    column.set_padding(left=4, right=5, top=4, bottom=4)

                    with column.column(align=Qt.AlignmentFlag.AlignTop) as widgets:
                        self.container = widgets

                scroll.setWidget(self.scroll_widget)

        self.hide_inputs()


    def on_menu_show(self):
        # Needed so the menu can resize properly
        self.scroll.updateGeometry()

    def show_inputs(self):
        self.scroll.setVisible(True)

    def hide_inputs(self):
        self.scroll.setVisible(False)



class LiveModeState(QObject):
    # When running live mode we poll for changes every 100 ms.
    POLL_DELAY = 100

    # When a change happens we wait this many milliseconds before
    # we run the workflow.
    DEBOUNCE_DELAY = 150 * 1000000


    def __init__(self, parent, extension):
        super().__init__(parent)

        self.extension = extension

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


    def is_changed(self, document, now, force_modified):
        # It's the first run, so we run immediately.
        if self.debounce_time is None:
            return True

        # Only run the workflow if modifications are enabled...
        if self.extension.live_mode_enabled:
            # ...and enough time has passed...
            if now >= self.debounce_time:
                # ...and the document changed.
                if force_modified or document.modified:
                    return True

        return False


    def check_changed(self, document, *, force_modified=False):
        if not self.is_running:
            return False

        if document is None:
            return False

        now = time.monotonic_ns()

        if self.is_changed(document, now, force_modified):
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
        self.extension.settings.node_metadata.changed.connect(self.on_metadata_changed)
        self.extension.settings.workflows.changed.connect(self.on_workflows_changed)

        self.selected_workflow =  self.extension.settings.settings.root.value("selected_workflow", str)
        self.selected_workflow.add_listener(self.on_workflow_changed)

        self.live_mode_enabled = self.extension.settings.with_selected_workflow(lambda x: x.value("live_mode_enabled", bool))
        self.live_mode_enabled.add_listener(self.on_live_mode_changed)

        self.document = DocumentManager(self)
        self.document.document_changed.connect(self.on_document_changed)
        self.document.layers_changed.connect(self.update_layer_inputs)

        self.live_mode_state = LiveModeState(self, self.extension)
        self.live_mode_state.timer.timeout.connect(self.maybe_run_live_mode)

        self.prompt_parser = PromptParser(self.extension.settings.bundles.root.get())

        self.layout = LayoutManager(self)

        self.workflow = Workflow(self.extension)

        self.layer_combo_options = self.get_layer_combo_options()
        self.ui_widgets = []
        self.ui_layer_inputs = []

        with self.layout.column() as column:
            with column.row() as row:
                row.set_padding(left=1, right=1, bottom=2)

                with row.widget(WorkflowSelector(tooltip="Workflow")) as combo:
                    self.workflow_selector = combo
                    combo.activated.connect(self.set_workflow)

                with row.tool_button(icon=Krita.icon("settings-button"), tooltip="Open settings") as button:
                    self.workflow_settings = WorkflowSettings(self.extension, self.extension.settings)
                    self.workflow_menu = Menu(self, self.workflow_settings)

                    # This is needed because we have to delay the menu resizing when closing a group.
                    self.workflow_menu_timer = QTimer(self)
                    self.workflow_menu_timer.setSingleShot(True)
                    self.workflow_menu_timer.setInterval(100)
                    self.workflow_menu_timer.timeout.connect(self.workflow_menu.refresh_size)

                    button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
                    button.setMenu(self.workflow_menu)

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

                scroll.setWidget(widget)

        self.update_workflow_selector()

        with self.catch_errors():
            self.workflow.initialize(
                self.document.current(),
                self.selected_workflow.get(),
            )
            self.workflow_selector.set_selected(self.workflow.id)
            self.update_widgets()


    def open_settings(self):
        self.extension.show_settings()


    def set_workflow(self):
        self.selected_workflow.set(self.workflow_selector.currentData())


    # If the widget has a link_to, we need to fetch the
    # node metadata and merge it into the widget info.
    def get_node_metadata(self, info):
        link_to = info.get("link_to", None)

        if link_to is None:
            return info

        else:
            new_info = {}

            metadata = self.extension.settings.node_metadata.get(link_to["node_id"]).input(link_to["input"])

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


    def add_widget(self, storage, parent, info, default_stretch, on_group_changed, defaults):
        info = self.get_node_metadata(info)

        match info["type"]:
            case "layer_id":
                widget = UiLayerId.from_json(self.workflow, storage, defaults, info, self.layer_combo_options)
                self.ui_widgets.append(widget)
                self.ui_layer_inputs.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "combo":
                widget = UiCombo.from_json(self.workflow, storage, defaults, info)
                self.ui_widgets.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "string":
                widget = UiString.from_json(self.workflow, storage, defaults, info)
                self.ui_widgets.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "prompt":
                widget = UiPrompt.from_json(self.workflow, storage, defaults, info, self.extension.settings)
                self.ui_widgets.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "boolean":
                widget = UiBoolean.from_json(self.workflow, storage, defaults, info)
                self.ui_widgets.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "int":
                widget = UiInt.from_json(self.workflow, storage, defaults, info)
                self.ui_widgets.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "float":
                widget = UiFloat.from_json(self.workflow, storage, defaults, info)
                self.ui_widgets.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "percentage":
                widget = UiFloat.from_json_percentage(self.workflow, storage, defaults, info)
                self.ui_widgets.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "label":
                assert not "enabled_if" in info
                widget = UiLabel.from_json(self.workflow, storage, defaults, info)
                self.ui_widgets.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "group":
                widget = UiGroup.from_json(self.workflow, storage, defaults, info)

                # TODO figure out a less hacky way of doing this
                if on_group_changed is not None:
                    widget.inputs.listeners.append(widget.inputs.value.add_listener(on_group_changed))

                for child in info["children"]:
                    self.add_widget(storage, widget.layout, child, default_stretch, on_group_changed, defaults)

                self.ui_widgets.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "row":
                assert not "enabled_if" in info

                widget = UiRow.from_json(self.workflow, storage, defaults, info)

                for child in info["children"]:
                    self.add_widget(storage, widget.layout, child, default_stretch, on_group_changed, defaults)

                self.ui_widgets.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "seed":
                widget = UiSeed.from_json(self.workflow, storage, defaults, info)
                self.ui_widgets.append(widget)
                parent.widget(widget, stretch=info.get("stretch", default_stretch))


            case "list":
                widget = UiList.from_json(self.workflow, storage, defaults, info,
                    # When an item is added, removed, or moved, it clears out all the
                    # existing widgets and remakes them from scratch.
                    #
                    # This is a performance cost, but it guarantees that the internal
                    # state will always be correct.
                    trigger_refresh=self.update_widgets,
                )

                for storage, layout in widget.make_children():
                    for child in info["children"]:
                        self.add_widget(storage, layout, child, default_stretch, on_group_changed, defaults)

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
        self.workflow_settings.container.clear()

        if self.workflow.is_loaded():
            if len(self.workflow.global_widgets) > 0:
                storage = (
                    self.extension.settings.settings.root.dict("workflows")
                        .dict(self.selected_workflow.get())
                        .dict("ui_inputs")
                )

                container = self.workflow_settings.container

                def on_group_changed():
                    self.workflow_menu.refresh_size()
                    self.workflow_menu_timer.start()

                for widget in self.workflow.global_widgets:
                    self.add_widget(storage, container, widget, 0, on_group_changed, {})

                container.stretch()

                self.workflow_settings.show_inputs()

                workflow_defaults = self.get_workflow_defaults()

            else:
                self.workflow_settings.hide_inputs()

                workflow_defaults = {}


            if len(self.workflow.document_widgets) > 0:
                for widget in self.workflow.document_widgets:
                    self.add_widget(self.workflow.root, self.widgets_container, widget, 0, None, workflow_defaults)

                self.widgets_container.stretch()


        else:
            with self.widgets_container.column(stretch=1, align=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter) as column:
                with column.row() as row:
                    with row.icon(Krita.icon("warning"), width=16, height=16) as icon:
                        icon.setContentsMargins(4, 4, 4, 4)

                    row.label(text="Not connected to ComfyUI")


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
                self.can_run_changed.emit()


    def on_workflow_changed(self):
        with self.catch_errors():
            if self.workflow.change_workflow(self.selected_workflow.get()):
                self.update_widgets()
                self.can_run_changed.emit()


    def on_document_changed(self):
        with self.catch_errors():
            self.stop_live_mode()

            if self.workflow.change_document(self.document.current()):
                self.layer_combo_options = self.get_layer_combo_options()
                self.update_widgets()
                self.can_run_changed.emit()
            else:
                self.update_layer_inputs()


    def can_run(self):
        return self.workflow.is_valid()


    def show_error(self, message, backtrace=None):
        self.stop_live_mode()
        MessageBox.error(self, text=message, details=backtrace)


    @contextlib.contextmanager
    def catch_errors(self):
        try:
            yield
        except Exception as e:
            self.stop_live_mode()
            MessageBox.from_exception(self, e)


    def get_workflow_defaults(self):
        defaults = {
            "seed/fixed": [],
            "seed/seed": [],
        }

        for widget in self.ui_widgets:
            if widget.is_default:
                inputs = widget.inputs

                if inputs.is_valid():
                    if isinstance(widget, UiSeed):
                        defaults["seed/fixed"].append(widget.seed.inputs.is_valid())
                        defaults["seed/seed"].append(widget.seed.inputs.value.get())

                    else:
                        input = inputs.value

                        if input is not None:
                            key = input.key()
                            values = defaults.get(key, None)

                            if values is None:
                                values = []
                                defaults[key] = values

                            values.append(input.get())

        return defaults


    def get_ui_values(self):
        ui_values = {
            "seed/fixed": [],
            "seed/seed": [],
        }

        for id in self.workflow.widget_ids:
            ui_values[id] = []

        normalize_weights = self.extension.settings.settings.root.value("normalize_danbooru_weights", bool).get()

        # Collects all of the UI inputs and puts their values into a flat array, organized by ID.
        for widget in self.ui_widgets:
            if not widget.is_default:
                inputs = widget.inputs

                if inputs.is_valid():
                    if isinstance(widget, UiSeed):
                        ui_values["seed/fixed"].append({
                            "value": widget.seed.inputs.is_valid(),
                        })
                        ui_values["seed/seed"].append({
                            "value": widget.seed.inputs.value.get(),
                        })

                    else:
                        input = inputs.value

                        if input is not None:
                            info = {
                                "value": input.get(),
                                "is_default": input.get() == input.default(),
                            }

                            if isinstance(widget, UiPrompt):
                                danbooru_tags = self.extension.settings.danbooru_tags.tags

                                parsed = self.prompt_parser.parse(input.get())

                                if normalize_weights:
                                    parsed.normalize_weights(parsed.positive, danbooru_tags)
                                    parsed.normalize_weights(parsed.negative, danbooru_tags)

                                parsed.convert_to_anima(parsed.positive, danbooru_tags)
                                parsed.convert_to_anima(parsed.negative, danbooru_tags)

                                info["positive"] = parsed.serialize(parsed.positive)
                                info["negative"] = parsed.serialize(parsed.negative)
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

                            ui_values[input.key()].append(info)

        return ui_values


    def run_workflow(self):
        self.extension.job_started.emit()

        with self.catch_errors():
            with Perf("run_workflow"):
                self.workflow.run_graph(
                    ui_values=self.get_ui_values(),
                    is_live_mode=False,
                    should_notify=True,
                )


    def run_live_workflow(self):
        with self.catch_errors():
            with Perf("run_live_workflow"):
                self.workflow.run_graph(
                    ui_values=self.get_ui_values(),
                    is_live_mode=True,
                    should_notify=False,
                )

                #assert not self.workflow.document.modified


    def is_live_mode_enabled(self):
        return self.live_mode_enabled.get()

    def is_live_mode_running(self):
        return self.live_mode_state.is_running


    def on_live_mode_changed(self):
        if not self.is_live_mode_enabled():
            self.stop_live_mode(emit=False)

        self.live_mode_changed.emit()


    def stop_live_mode(self, *, emit=True):
        if self.live_mode_state.stop():
            self.extension.client.clear_queue_live_mode()

            # TODO more robust way to handle this
            if self.workflow.document is not None:
                self.workflow.document.modified = True

            if emit:
                self.live_mode_changed.emit()


    def maybe_run_live_mode(self, *, force_modified=False, notify_job_started=True):
        is_changed = self.live_mode_state.check_changed(self.workflow.document, force_modified=force_modified)

        if is_changed:
            if notify_job_started:
                self.extension.job_started.emit()

            self.run_live_workflow()


    def toggle_live_mode_running(self):
        if self.is_live_mode_running():
            self.stop_live_mode()
        else:
            if self.live_mode_state.start():
                self.maybe_run_live_mode()
                self.live_mode_changed.emit()

import krita
from krita import DockWidget
from PyQt6.QtCore import QObject, QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QToolButton,
    QHBoxLayout,
    QVBoxLayout,
    QWidgetAction,
    QWidget,
    QLayout,
)
from ..extension import ComfyUIExtension
from ..server import GraphInfo, GraphState
from ..ui.workflow import UiInputs
from ..ui.workflow.widgets import UiLayerId, UiCombo, UiInt, UiFloat, UiString, UiStringMultiline, UiGroup, UiRow, UiList
from ..util import number_of_decimals
from ..util.krita import Document, Layer, Image, Bounds, DocumentManager, get_extension
from ..util.graph import Graph
from ..util.qt import LayoutManager, MessageBox, BlockSignals
from ..util.workflow import Workflow, WorkflowError


class JobWidget(QWidget):
    def __init__(self, client, info):
        super().__init__()

        self.client = client
        self.layout = LayoutManager(self)

        with self.layout.row() as row:
            row.spacer(4)

            with row.label(tooltip="Status") as label:
                self.icon = label

            row.spacer(6)

            with row.progress_bar(minimum=0, maximum=1000000, tooltip="Progress") as progress:
                self.progress = progress

            with row.tool_button(icon=Krita.icon("dialog-cancel"), tooltip="Cancel") as button:
                button.clicked.connect(self.cancel_job)

        self.update_info(info)


    def update_progress_bar(self, progress_bar):
        # @TODO don't hardcode the maximum
        progress_bar.setValue(int(self.info.progress * 1000000.0))


    def update_info(self, info):
        self.info = info

        self.icon.setPixmap(self.info.state.status_icon().pixmap(16, 16))

        self.update_progress_bar(self.progress)


    def cancel_job(self):
        self.client.stop_execute_graph(self.info.graph_id)



class QueueList(QListWidget):
    def __init__(self):
        super().__init__()

        #self.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        #self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed))
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.setStyleSheet("QListWidget { background-color: transparent; }")

        self.jobs = []


    def add_job(self, client, info):
        job = JobWidget(client, info)
        self.jobs.append(job)

        item = QListWidgetItem()
        item.setSizeHint(job.sizeHint())

        self.addItem(item)
        self.setItemWidget(item, job)


    def update_job(self, info):
        for job in self.jobs:
            if job.info.graph_id == info.graph_id:
                job.update_info(info)
                return True

        return False


    def find_job(self, graph_id):
        for index, job in enumerate(self.jobs):
            if job.info.graph_id == graph_id:
                return index


    def remove_job(self, info):
        index = self.find_job(info.graph_id)
        assert index is not None

        job = self.jobs.pop(index)
        item = self.takeItem(index)

        self.removeItemWidget(item)

        job.deleteLater()


    def process_graph_info(self, client, info):
        if info.state.is_ended():
            self.remove_job(info)
        else:
            if not self.update_job(info):
                self.add_job(client, info)


class QueueWidget(QWidget):
    def __init__(self):
        super().__init__()

        self.layout = LayoutManager(self)

        with self.layout.column() as column:
            #column.setContentsMargins(4, 0, 4, 0)
            #column.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

            with column.row() as row:
                row.stretch()

                row.label(text="Queue")

                row.stretch()

                #with self.layout.tool_button() as button:
                    #button.setIcon(Krita.icon("animation_pause"))
                    #button.clicked.connect(self.pause_jobs)
                    #row.addWidget(button)

                #with self.layout.tool_button() as button:
                    #button.setIcon(Krita.icon("dialog-cancel"))
                    #button.clicked.connect(self.cancel_jobs)
                    #row.addWidget(button)

            #with self.layout.button() as button:
                #button.setText("Hi")
                #column.addWidget(button)

            self.queue_list = QueueList()
            column.widget(self.queue_list)


    #def pause_jobs(self):
        #pass

    #def cancel_jobs(self):
        #pass


    def jobs_len(self):
        return len(self.queue_list.jobs)

    def get_first_job(self):
        if len(self.queue_list.jobs) > 0:
            return self.queue_list.jobs[0]

    def process_graph_info(self, client, info):
        self.queue_list.process_graph_info(client, info)


class WorkflowWidget(QWidget):
    def __init__(self, extension):
        super().__init__()

        self.extension = extension
        self.extension.settings.node_metadata_changed.connect(self.update_widgets)

        self.document = DocumentManager(self)
        self.document.document_changed.connect(self.on_document_changed)
        self.document.layers_changed.connect(self.update_layer_inputs)

        self.layout = LayoutManager(self)

        self.ui_layout = {
            "children": [
                {
                    "type": "percentage",
                    "id": "image_weight",
                    "link_to": {
                        "node_id": "prompt_helpers: EZImage",
                        "input": "image_weight",
                    },
                    "step": 0.05,
                },

                {
                    "type": "string",
                    "id": "prompt",
                    "multiline": True,
                    "tooltip": "Prompt",
                    "placeholder": "Prompt...",
                },

                {
                    "type": "layer_id",
                    "id": "layer",
                },

                {
                    "type": "group",
                    "id": "controlnet_group",
                    "title": "Control Nets",
                    "default": False,
                    "children": [
                        {
                            "type": "list",
                            "id": "controlnet_list",
                            "children": [
                                {
                                    "type": "layer_id",
                                    "id": "controlnet_layer",
                                    "tooltip": "Control Net Layer",
                                },

                                {
                                    "type": "row",
                                    "children": [
                                        {
                                            "type": "combo",
                                            "id": "controlnet_model",
                                            "link_to": {
                                                "node_id": "ControlNetLoader",
                                                "input": "control_net_name",
                                            },
                                        },
                                        {
                                            "type": "combo",
                                            "id": "controlnet_type",
                                            "link_to": {
                                                "node_id": "SetUnionControlNetType",
                                                "input": "type",
                                            },
                                            "default": "auto",
                                        },
                                    ],
                                },

                                {
                                    "type": "percentage",
                                    "id": "controlnet_start",
                                    "tooltip": "Start Percentage",
                                    "default": 0.0,
                                    "step": 0.05,
                                },

                                {
                                    "type": "percentage",
                                    "id": "controlnet_end",
                                    "tooltip": "End Percentage",
                                    "default": 0.3,
                                    "step": 0.05,
                                },

                                {
                                    "type": "percentage",
                                    "id": "controlnet_weight",
                                    "tooltip": "Weight",
                                    "default": 0.5,
                                    "step": 0.05,
                                },
                            ],
                        },
                    ],
                },

                {
                    "type": "group",
                    "id": "advanced",
                    "title": "Advanced",
                    "default": False,
                    "children": [
                        {
                            "type": "row",
                            "children": [
                                {
                                    "type": "combo",
                                    "id": "checkpoint",
                                    "link_to": {
                                        "node_id": "prompt_helpers: EZCheckpoint",
                                        "input": "checkpoint",
                                    },
                                },

                                {
                                    "type": "int",
                                    "id": "clip_skip",
                                    "link_to": {
                                        "node_id": "prompt_helpers: EZCheckpoint",
                                        "input": "clip_skip",
                                    },
                                },
                            ],
                        },

                        {
                            "type": "row",
                            "children": [
                                {
                                    "type": "combo",
                                    "id": "sampler_name",
                                    "link_to": {
                                        "node_id": "prompt_helpers: EZSampler",
                                        "input": "sampler_name",
                                    },
                                },

                                {
                                    "type": "combo",
                                    "id": "scheduler",
                                    "link_to": {
                                        "node_id": "prompt_helpers: EZSampler",
                                        "input": "scheduler",
                                    },
                                },

                                {
                                    "type": "int",
                                    "id": "steps",
                                    "link_to": {
                                        "node_id": "prompt_helpers: EZSampler",
                                        "input": "steps",
                                    },
                                    "suffix": " steps",
                                },
                            ],
                        },

                        {
                            "type": "row",
                            "children": [
                                {
                                    "type": "float",
                                    "id": "prompt_weight",
                                    "link_to": {
                                        "node_id": "prompt_helpers: EZPrompt",
                                        "input": "weight",
                                    },
                                    "suffix": " cfg",
                                    "default": 5.0,
                                },

                                {
                                    "type": "float",
                                    "id": "detail_megapixels",
                                    "link_to": {
                                        "node_id": "prompt_helpers: EZDetail",
                                        "input": [
                                            "resize_type",
                                            "scale total pixels",
                                            "megapixels",
                                        ],
                                    },
                                    "suffix": " megapixels",
                                },
                            ],
                        },
                    ],
                },
            ],
        }

        self.ui_inputs = UiInputs()
        self.ui_inputs.setParent(self)
        self.ui_inputs.load_document(self.document.current())

        self.error = MessageBox(QMessageBox.Icon.Critical, "Workflow error", "", parent=self)
        self.error.setSizeGripEnabled(True)
        self.error.setTextFormat(Qt.TextFormat.PlainText)

        self.normal_inputs = []
        self.layer_inputs = []

        with self.layout.column() as column:
            with column.row() as row:
                row.set_padding(left=2, right=2, bottom=4)

                with row.combo_box(tooltip="Workflow") as combo:
                    self.workflow_name = combo

                    combo.currentTextChanged.connect(self.on_workflow_changed)

                    for name in self.extension.settings.all_workflows:
                        combo.addItem(Krita.icon("bookmarks"), name)

                with row.tool_button(icon=Krita.icon("properties"), tooltip="Open settings") as button:
                    button.clicked.connect(self.open_settings)

            with column.scroll() as scroll:
                widget = QWidget()
                layout = LayoutManager(widget)

                # Causes the children to shrink horizontally, to avoid a horizontal scrollbar
                widget.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred))

                with layout.column() as column:
                    column.set_padding(left=8, right=8)
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

            metadata = self.extension.settings.get_node_metadata(link_to["node_id"])

            input = link_to["input"]

            if isinstance(input, str):
                metadata = metadata.input(input)
            else:
                for name in input:
                    metadata = metadata.input(name)

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
            for name in ("default", "min", "max", "step", "tooltip", "multiline", "placeholder"):
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
                )

                with parent.widget(widget) as widget:
                    self.layer_inputs.append(widget)


            case "combo":
                widget = UiCombo(
                    inputs.input(info["id"], index),
                    tooltip=info.get("tooltip", None),
                    default=info.get("default", ""),
                    values=info.get("values", []),
                )

                with parent.widget(widget) as widget:
                    self.normal_inputs.append(widget)


            case "string":
                multiline = info.get("multiline", False)

                if multiline:
                    widget = UiStringMultiline(
                        inputs.input(info["id"], index),
                        tooltip=info.get("tooltip", None),
                        default=info.get("default", ""),
                        placeholder=info.get("placeholder", None),
                        background_color=info.get("background_color", None),
                        min_lines=info.get("min_lines", 2),
                        max_lines=info.get("max_lines", 6),
                    )

                else:
                    widget = UiString(
                        inputs.input(info["id"], index),
                        tooltip=info.get("tooltip", None),
                        default=info.get("default", ""),
                        placeholder=info.get("placeholder", None),
                    )

                with parent.widget(widget) as widget:
                    self.normal_inputs.append(widget)


            case "int":
                widget = UiInt(
                    inputs.input(info["id"], index),
                    tooltip=info.get("tooltip", None),
                    slider=info.get("slider", False),
                    default=info.get("default", 0),
                    # 32-bit signed integer
                    min=info.get("min", -2147483648),
                    max=info.get("max", 2147483647),
                    step=info.get("step", 1),
                    suffix=info.get("suffix", None),
                )

                with parent.widget(widget) as widget:
                    self.normal_inputs.append(widget)


            case "float":
                widget = UiFloat(
                    inputs.input(info["id"], index),
                    tooltip=info.get("tooltip", None),
                    slider=info.get("slider", False),
                    default=info.get("default", 0.0),
                    min=info.get("min", 0.0),
                    max=info.get("max", 1.0),
                    step=info.get("step", 0.01),
                    multiplier=info.get("multiplier", None),
                    suffix=info.get("suffix", None),
                    decimals=info.get("decimals", 2),
                )

                with parent.widget(widget) as widget:
                    self.normal_inputs.append(widget)


            case "percentage":
                widget = UiFloat(
                    inputs.input(info["id"], index),
                    tooltip=info.get("tooltip", None),
                    slider=info.get("slider", True),
                    default=info.get("default", 0.0),
                    min=0.0,
                    max=1.0,
                    step=info.get("step", 0.01),
                    multiplier=100.0,
                    suffix="%",
                    decimals=info.get("decimals", 0),
                )

                with parent.widget(widget) as widget:
                    self.normal_inputs.append(widget)


            case "group":
                widget = UiGroup(
                    inputs.input(info["id"], index),
                    title=info.get("title", ""),
                    default=info.get("default", True),
                )

                with parent.widget(widget) as widget:
                    self.normal_inputs.append(widget)

                    for child in info["children"]:
                        self.add_widget(inputs, widget.layout, child, index)


            case "row":
                with parent.widget(UiRow()) as widget:
                    for child in info["children"]:
                        self.add_widget(inputs, widget.layout, child, index)


            case "list":
                widget = UiList(
                    inputs.input(info["id"], index),
                    inputs=inputs,
                    start_index=index,
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
        self.normal_inputs = []

        for widget in self.ui_layout["children"]:
            self.add_widget(self.ui_inputs, self.widgets, widget, 0)

        self.widgets.stretch()
        self.update_inputs()


    def update_layer_inputs(self):
        print("Updating layers")

        layers = self.document.layers

        for input in self.layer_inputs:
            with BlockSignals(input):
                input.set_layers(layers)
                input.reset()


    def update_inputs(self):
        self.update_layer_inputs()

        for input in self.normal_inputs:
            input.reset()


    def on_workflow_changed(self, text):
        print("WORKFLOW NAME", text)


    def on_document_changed(self):
        print("CHANGED")
        document = self.document.current()

        self.ui_inputs.load_document(document)

        print(self.ui_inputs.current())

        self.update_widgets()


    def test_graph():
        graph = Graph()

        parse_lines = graph.node("prompt_helpers: ParseLines", text="1girl").out(0)

        checkpoint = graph.node("prompt_helpers: EZCheckpoint", checkpoint="illustrious/novaPolyXL_v20.safetensors", clip_skip=2)

        prompt = graph.node("prompt_helpers: EZPrompt", json=parse_lines, weight=5.0)

        import random
        seed = random.randint(0, 10000000)

        sampler = graph.node("prompt_helpers: EZSampler", sampler_name="euler", scheduler="normal", steps=30, seed=seed)

        image = graph.node("prompt_helpers: EZBlank", width=1024, height=1024)

        image = graph.node("prompt_helpers: EZBatch", image_settings=image.out(0), batch_size=4, select_index=-1)

        generate = graph.node(
            "prompt_helpers: EZGenerate",
            model=checkpoint.out(0),
            clip=checkpoint.out(1),
            vae=checkpoint.out(2),
            #folder="tmp",
            #filename="%timestamp%",
            prompt=prompt.out(0),
            sampler=sampler.out(0),
            image=image.out(0),
            control_net=None,
        )

        graph.node("krita_comfyui: KritaOutput", images=generate.out(0), x=0, y=0, name="ComfyUI [%index%]")
        #graph.node("PreviewImage", images=generate.out(0))

        #graph.node("krita_comfyui: KritaText", text="Testing", name="Foo")

        #graph.node("krita_comfyui: KritaText", text=image.out(0), name="Image Text")

        #graph.node("PreviewAny", source=graph.node("CheckpointLoaderSimple", ckpt_name=).out(0))

        return graph


    def can_run_workflow(self):
        has_document = self.document.current() is not None

        workflow_name = self.workflow_name.currentText()

        return has_document and workflow_name != ""


    def show_error(self, message, backtrace=None):
        self.error.setText(message)

        if backtrace is None:
            self.error.setDetailedText("")
        else:
            self.error.setDetailedText(backtrace)

        self.error.exec()


    def run_workflow(self):
        document = self.document.current()

        if document is None:
            raise RuntimeError("Krita does not have an opened image")

        workflow_name = self.workflow_name.currentText()

        if workflow_name == "":
            raise RuntimeError("Workflow cannot be empty")

        json = self.extension.settings.load_workflow(workflow_name)

        seed = Workflow.random_seed()

        print(self.ui_inputs.current())

        workflow = Workflow(
            document=document,
            json=json,
            seed=seed,
            ui_values=self.ui_inputs.current(),
        )

        try:
            graph = workflow.to_graph()

        except WorkflowError as e:
            self.show_error(message=str(e))

        self.extension.client.execute_graph(graph)


    def open_settings(self):
        self.extension.show_settings()


class InputsWidget(QWidget):
    def __init__(self):
        super().__init__()

        self.extension = get_extension(ComfyUIExtension)
        self.extension.client.graph_changed.connect(self.on_graph_changed)
        self.extension.client.connection_changed.connect(self.update_run_button)

        self.layout = LayoutManager(self)

        with self.layout.column() as column:
            self.workflow = WorkflowWidget(self.extension)
            self.workflow.document.document_changed.connect(self.update_run_button)
            self.workflow.workflow_name.currentTextChanged.connect(self.update_run_button)
            column.widget(self.workflow)

            #with self.layout.column() as inputs:
                #column.addLayout(inputs)

            with column.row() as row:
                row.set_padding(left=10, right=2, bottom=2)

                with row.progress_bar(minimum=0, maximum=1000000, tooltip="Progress") as progress:
                    self.progress_bar = progress
                    progress.setValue(0)

                with row.tool_button(tooltip="Run workflow in ComfyUI") as button:
                    self.run_button = button

                    self.queue_menu = QMenu(self)
                    self.queue = QueueWidget()

                    widget_action = QWidgetAction(self.queue_menu)
                    widget_action.setDefaultWidget(self.queue)
                    self.queue_menu.addAction(widget_action)

                    for info in self.extension.client.current_queue():
                        self.queue.process_graph_info(self.extension.client, info)

                    self.update()

                    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                    button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
                    button.setMenu(self.queue_menu)
                    button.clicked.connect(self.workflow.run_workflow)

        self.update_run_button()


    def on_graph_changed(self, info):
        if info.state.is_error():
            self.workflow.show_error(
                message=info.error.format(),
                backtrace=info.error.backtrace,
            )

        self.queue.process_graph_info(self.extension.client, info)
        self.update()


    def update_run_button(self):
        self.run_button.setEnabled(self.extension.client.is_connected and self.workflow.can_run_workflow())


    def update(self):
        len = self.queue.jobs_len()

        if len == 0:
            self.run_button.setText("Run")
        else:
            self.run_button.setText(f"Run [{len}]")


        current_job = self.queue.get_first_job()

        if current_job is None:
            self.run_button.setIcon(GraphState.Idle.button_icon())
            self.progress_bar.setValue(0)

        else:
            self.run_button.setIcon(current_job.info.state.button_icon())
            current_job.update_progress_bar(self.progress_bar)


class ComfyUIInputWidget(DockWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ComfyUI Inputs")

        #self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred))

        self._inputs = InputsWidget()
        self.setWidget(self._inputs)

    def canvasChanged(self, _canvas: krita.Canvas):
        print("canvasChanged")
        self._inputs.workflow.document.check_changes()

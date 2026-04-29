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
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QWidgetAction,
    QWidget,
    QLayout,
)
from ..extension import ComfyUIExtension
from ..server import GraphInfo, GraphState
from ..ui.workflow import UiInputs
from ..ui.workflow.widgets import UiLayerId
from ..util.krita import Document, Layer, Image, Bounds, BlockSignals, DocumentManager, get_extension
from ..util.graph import Graph
from ..util.qt import LayoutManager
from ..util.workflow import Workflow


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

        self.document = DocumentManager(self)
        self.document.document_changed.connect(self.on_document_changed)
        self.document.layers_changed.connect(self.update_layer_inputs)

        self.layout = LayoutManager(self)

        self.ui_inputs = UiInputs()
        self.ui_inputs.setParent(self)
        self.ui_inputs.load_document(self.document.current())

        self.layer_inputs = []

        with self.layout.column() as column:
            with column.row() as row:
                with row.combo_box(tooltip="Workflow") as combo:
                    self.workflow_name = combo

                    combo.currentTextChanged.connect(self.on_workflow_changed)

                    for name in self.extension.settings.all_workflows:
                        combo.addItem(Krita.icon("bookmarks"), name)

                with row.tool_button(icon=Krita.icon("properties"), tooltip="Open settings") as button:
                    button.clicked.connect(self.open_settings)

            with column.widget(UiLayerId(self.ui_inputs.input("layer", 0), tooltip="Layer")) as layer_id:
                self.layer_inputs.append(layer_id)

        self.update_layer_inputs()


    def update_layer_inputs(self):
        print("Updating layers")

        layers = self.document.layers

        for input in self.layer_inputs:
            with BlockSignals(input):
                input.clear()

                input.add(text="", data="")

                for layer in layers:
                    if layer is None:
                        input.separator()
                    else:
                        input.add(icon=layer.type.icon(), text=layer.name, data=layer.id)

                input.reset()


    def on_workflow_changed(self, text):
        print("WORKFLOW NAME", text)


    def on_document_changed(self):
        print("CHANGED")
        document = self.document.current()

        self.ui_inputs.load_document(document)

        print(self.ui_inputs.current())

        self.update_layer_inputs()


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

        graph = workflow.to_graph()

        self.extension.client.execute_graph(graph)


    def open_settings(self):
        self.extension.show_settings()


class InputsWidget(QWidget):
    def __init__(self):
        super().__init__()

        self.extension = get_extension(ComfyUIExtension)
        self.extension.client.graph_changed.connect(self.on_graph_changed)

        self.layout = LayoutManager(self)

        with self.layout.column() as column:
            self.workflow = WorkflowWidget(self.extension)
            self.workflow.document.document_changed.connect(self.update_run_button)
            self.workflow.workflow_name.currentTextChanged.connect(self.update_run_button)
            column.widget(self.workflow)

            #with self.layout.column() as inputs:
                #column.addLayout(inputs)

            column.stretch()

            with column.row() as row:
                row.set_padding(left=8, top=0, right=4, bottom=2)

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


    def on_graph_changed(self, info):
        self.queue.process_graph_info(self.extension.client, info)
        self.update()


    def update_run_button(self):
        self.run_button.setEnabled(self.workflow.can_run_workflow())


    def update(self):
        len = self.queue.jobs_len()

        if len == 0:
            self.run_button.setText("Run")
        else:
            self.run_button.setText("Run [{}]".format(len))


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

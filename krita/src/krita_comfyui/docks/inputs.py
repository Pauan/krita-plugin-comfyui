import krita
from krita import DockWidget
from PyQt6.QtCore import QPoint, QSize, Qt, pyqtSignal
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
from ..layer import Document, Layer, Image, Bounds, BlockSignals
from ..server import GraphInfo, GraphState
from ..graph import Graph
from ..qt import Layout


class Job(QWidget):
    def __init__(self, parent, client, info):
        super().__init__(parent)

        self.client = client
        self.layout = Layout(self)

        with self.layout.row() as row:
            row.addSpacing(4)

            with self.layout.label() as label:
                self.icon = label
                row.addWidget(label)

            row.addSpacing(6)

            with self.layout.progress_bar() as progress:
                progress.setMinimum(0)
                progress.setMaximum(1000000)
                self.progress = progress
                row.addWidget(progress)

            with self.layout.tool_button() as button:
                button.setIcon(Krita.icon("dialog-cancel"))
                button.clicked.connect(self.cancel_job)
                row.addWidget(button)

            self.setLayout(row)

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
    def __init__(self, parent: QWidget | None):
        super().__init__(parent)

        #self.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        #self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed))
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.setStyleSheet("QListWidget { background-color: transparent; }")

        self.jobs = []


    def add_job(self, client, info):
        job = Job(self, client, info)
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
    def __init__(self, parent):
        super().__init__(parent)

        self.layout = Layout(self)

        with self.layout.column() as column:
            #column.setContentsMargins(4, 0, 4, 0)
            #column.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

            with self.layout.row() as row:
                row.addStretch()

                with self.layout.label() as label:
                    label.setText("Queue")
                    row.addWidget(label)

                row.addStretch()

                #with self.layout.tool_button() as button:
                    #button.setIcon(Krita.icon("animation_pause"))
                    #button.clicked.connect(self.pause_jobs)
                    #row.addWidget(button)

                #with self.layout.tool_button() as button:
                    #button.setIcon(Krita.icon("dialog-cancel"))
                    #button.clicked.connect(self.cancel_jobs)
                    #row.addWidget(button)

                column.addLayout(row)

            #with self.layout.button() as button:
                #button.setText("Hi")
                #column.addWidget(button)

            self.queue_list = QueueList(self)
            column.addWidget(self.queue_list)

            self.setLayout(column)


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


class InputsWidget(QWidget):
    def __init__(self, parent):
        super().__init__(parent)

        self.extension = None

        for extension in Krita.extensions():
            if isinstance(extension, ComfyUIExtension):
                assert self.extension is None
                self.extension = extension

        self.extension.client.graph_changed.connect(self.on_graph_changed)

        self.layout = Layout(self)

        with self.layout.column() as column:
            #with self.layout.column() as inputs:
                #column.addLayout(inputs)

            column.addStretch()

            with self.layout.row() as row:
                with self.layout.progress_bar() as progress:
                    self.progress_bar = progress
                    progress.setMinimum(0)
                    progress.setMaximum(1000000)
                    progress.setValue(0)
                    row.addWidget(progress)

                with self.layout.tool_button() as button:
                    self.run_button = button

                    self.queue_menu = QMenu(self)
                    self.queue = QueueWidget(self.queue_menu)

                    widget_action = QWidgetAction(self.queue_menu)
                    widget_action.setDefaultWidget(self.queue)
                    self.queue_menu.addAction(widget_action)

                    for info in self.extension.client.current_queue():
                        self.queue.process_graph_info(self.extension.client, info)

                    self.update()

                    button.setToolTip("Run workflow in ComfyUI")
                    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                    button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
                    button.setMenu(self.queue_menu)
                    button.clicked.connect(self.run_workflow)
                    row.addWidget(button)

                row.setContentsMargins(8, 0, 4, 2)
                column.addLayout(row)


    def on_graph_changed(self, info):
        self.queue.process_graph_info(self.extension.client, info)
        self.update()


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


    def run_workflow(self):
        graph = Graph()

        parse_lines = graph.node("prompt_helpers: ParseLines", text="1girl").out(0)

        checkpoint = graph.node("prompt_helpers: EZCheckpoint", checkpoint="illustrious/novaPolyXL_v20.safetensors", clip_skip=2)

        prompt = graph.node("prompt_helpers: EZPrompt", json=parse_lines, weight=5.0)

        import random
        seed = random.randint(0, 10000000)

        sampler = graph.node("prompt_helpers: EZSampler", sampler_name="euler", scheduler="normal", steps=30, seed=seed)

        image = graph.node("prompt_helpers: EZBlank", width=1024, height=1024)

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

        graph.node("PreviewImage", images=generate.out(0))

        #graph.node("PreviewAny", source=graph.node("CheckpointLoaderSimple", ckpt_name=).out(0))

        self.extension.client.execute_graph(graph)


class ComfyUIInputWidget(DockWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ComfyUI Inputs")

        #self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred))

        self._inputs = InputsWidget(self)

        self.setWidget(self._inputs)


    def canvasChanged(self, canvas: krita.Canvas):
        pass


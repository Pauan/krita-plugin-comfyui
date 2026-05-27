from krita import DockWidget
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QToolButton,
    QWidgetAction,
    QWidget,
)
from ..extension import ComfyUIExtension
from ..server import GraphState
from ..util.krita import get_extension
from ..util.qt import LayoutManager
from ..workflow.widget import WorkflowWidget
from ..workflow.ui import UiBoolean, UiInt
from ..workflow.graph import WorkflowGraph
from ..shared import MIN_SEED, MAX_SEED


class JobWidget(QWidget):
    def __init__(self, client, info):
        super().__init__()

        self.client = client
        self.layout = LayoutManager(self)

        with self.layout.row() as row:
            row.spacer(4)

            with row.label() as label:
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

        self.icon.setToolTip(self.info.state.status_text())
        self.icon.setPixmap(self.info.state.status_icon().pixmap(16, 16))

        self.update_progress_bar(self.progress)


    def cancel_job(self):
        self.client.stop_execute_graph(self.info.graph_id)



class QueueList(QListWidget):
    def __init__(self):
        super().__init__()

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

        # If index is None then the graph had immediately errored.
        if index is not None:
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
    def __init__(self, settings):
        super().__init__()

        self.settings = settings

        self.layout = LayoutManager(self)

        with self.layout.column() as column:
            # TODO cleanup listeners when dock is removed
            widget = UiBoolean.from_json(self.settings, {
                "id": "live_mode_enabled",
                "tooltip": "Enable live mode, which automatically generates new images.",
                "label": "Enable live mode.",
            })

            column.widget(widget)

            with column.row() as row:
                # TODO cleanup listeners when dock is removed
                widget = UiBoolean.from_json(self.settings, {
                    "id": "fixed_seed_enabled",
                    "tooltip": "If true it will use a fixed seed.\nIf false it will generate a random seed every time.",
                })

                row.widget(widget)

                # TODO cleanup listeners when dock is removed
                widget = UiInt.from_json(self.settings, {
                    "id": "fixed_seed",
                    "tooltip": f"Fixed seed between {MIN_SEED} and {MAX_SEED}",
                    "min": MIN_SEED,
                    "max": MAX_SEED,
                    "prefix": "Seed: ",
                    "enabled_if": {
                        "id": "fixed_seed_enabled",
                        "value": True,
                    },
                })

                row.widget(widget, stretch=1)

                with row.tool_button(icon=Krita.icon("reload-preset"), tooltip="Generate random seed.") as button:
                    self.seed_button = button
                    self.seed_button.clicked.connect(self.generate_random_seed)

                    # TODO cleanup listeners when dock is removed
                    self.settings.item("fixed_seed_enabled").with_value(self.seed_button.setEnabled)


            with column.row(align=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop) as row:
                row.label(text="Job Queue")

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


    def generate_random_seed(self):
        self.settings.item("fixed_seed").set(WorkflowGraph.random_seed())


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
    def __init__(self):
        super().__init__()

        self.extension = get_extension(ComfyUIExtension)
        self.extension.client.graph_changed.connect(self.on_graph_changed)
        self.extension.client.connection_changed.connect(self.on_connection_changed)

        self.is_connected = self.extension.client.is_connected()

        self.layout = LayoutManager(self)

        with self.layout.column() as column:
            self.workflow = WorkflowWidget(self.extension)
            self.workflow.can_run_changed.connect(self.update_run_button)
            self.workflow.live_mode_changed.connect(self.update_run_button)
            column.widget(self.workflow)

            with column.row() as row:
                row.set_padding(left=9, right=1, bottom=1, top=1)

                with row.progress_bar(minimum=0, maximum=1000000, tooltip="Progress") as progress:
                    self.progress_bar = progress
                    progress.setValue(0)

                with row.tool_button() as button:
                    self.run_button = button

                    self.queue_menu = QMenu(self)
                    self.queue = QueueWidget(self.extension.settings.settings)

                    widget_action = QWidgetAction(self.queue_menu)
                    widget_action.setDefaultWidget(self.queue)
                    self.queue_menu.addAction(widget_action)

                    for info in self.extension.client.current_queue():
                        self.queue.process_graph_info(self.extension.client, info)

                    self.update_run_button()

                    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                    button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
                    button.setMenu(self.queue_menu)
                    button.clicked.connect(self.on_click)

        self.update_run_button()


    def on_connection_changed(self, connected):
        self.is_connected = connected
        self.update_run_button()


    def on_graph_changed(self, info):
        if info.state.is_error():
            self.workflow.stop_live_mode()

            self.workflow.show_error(
                message=info.error.format(),
                backtrace=info.error.backtrace,
            )

        self.queue.process_graph_info(self.extension.client, info)

        if info.state.is_success():
            self.workflow.maybe_run_live_mode()

        self.update_run_button()


    def update_run_button_live(self, tooltip):
        is_running = self.workflow.is_live_mode_running()


        if tooltip is None:
            if is_running:
                self.run_button.setToolTip("Stop live mode")
            else:
                self.run_button.setToolTip("Start live mode")
        else:
            self.run_button.setToolTip(tooltip)


        if is_running:
            self.run_button.setText("Stop")
            self.run_button.setIcon(GraphState.Executing.button_icon())
        else:
            self.run_button.setText("Start")
            self.run_button.setIcon(GraphState.Idle.button_icon())


    def update_run_button_normal(self, tooltip, current_job):
        if tooltip is None:
            self.run_button.setToolTip("Run workflow in ComfyUI")
        else:
            self.run_button.setToolTip(tooltip)


        len = self.queue.jobs_len()

        if len == 0:
            self.run_button.setText("Run")
        else:
            self.run_button.setText(f"Run [{len}]")


        if current_job is None:
            self.run_button.setIcon(GraphState.Idle.button_icon())
        else:
            self.run_button.setIcon(current_job.info.state.button_icon())


    def update_run_button(self):
        current_job = self.queue.get_first_job()

        if current_job is None:
            self.progress_bar.setValue(0)
        else:
            current_job.update_progress_bar(self.progress_bar)


        if not self.is_connected:
            tooltip = "Not connected to ComfyUI"
        elif not self.workflow.can_run():
            tooltip = "No workflow selected"
        else:
            tooltip = None


        self.run_button.setEnabled(tooltip is None)

        if self.workflow.is_live_mode_enabled():
            self.update_run_button_live(tooltip)
        else:
            self.update_run_button_normal(tooltip, current_job)


    def on_click(self):
        if self.workflow.is_live_mode_enabled():
            self.workflow.toggle_live_mode_running()
        else:
            self.workflow.run_workflow()


class ComfyUIInputWidget(DockWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ComfyUI Inputs")

        self._inputs = InputsWidget()
        self.setWidget(self._inputs)

    def canvasChanged(self, _canvas):
        self._inputs.workflow.document.check_changes()

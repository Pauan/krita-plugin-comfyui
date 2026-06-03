import contextlib
from krita import DockWidgetFactory, DockWidgetFactoryBase, Extension
from PyQt6.QtCore import pyqtSignal

from .server import ComfyUIClient
from .settings import Settings
from .settings.dialog import SettingsDialog
from .util.notify import NotifyWorker
from .util.qt import Thread


class ComfyUIExtension(Extension):
    job_started = pyqtSignal()


    def __init__(self, parent):
        super().__init__(parent)

        self.live_mode_enabled = True

        self.notify = NotifyWorker()

        # The notifier needs to run async functions.
        # Instead of connecting Python's async event loop into the QEventLoop,
        # it's easier to just run it on a separate thread.
        self.notify_thread = Thread(self)
        self.notify_thread.move(self.notify)

        self.settings = Settings(self)
        self.settings.clear_log()

        self.client = ComfyUIClient(self.settings, url="127.0.0.1:8188", reconnect_delay=10000)

        # We execute jobs in a separate thread so it doesn't freeze the UI.
        self.client_thread = Thread(self)
        # We immediately connect to ComfyUI so we can update the node metadata
        self.client_thread.started.connect(self.client.connect)
        self.client_thread.move(self.client)

        self.client.graph_changed.connect(self.on_graph_changed)

        self.settings_dialog = SettingsDialog(self, self.settings)

        notifier = parent.notifier()
        notifier.setActive(True)
        notifier.applicationClosing.connect(self.shutdown)


    @contextlib.contextmanager
    def disable_live_mode(self):
        live_mode_enabled = self.live_mode_enabled
        try:
            self.live_mode_enabled = False
            yield
        finally:
            self.live_mode_enabled = live_mode_enabled


    def show_settings(self):
        self.settings_dialog.show()


    def createActions(self, window):
        pass


    def setup(self):
        self.notify_thread.start()
        self.client_thread.start()


    def on_graph_changed(self, graph):
        if graph.state.is_success():
            if graph.should_notify:
                self.notify.message.emit("Job finished")

        elif graph.state.is_error():
            self.notify.message.emit("Job errored!")


    def shutdown(self):
        self.settings_dialog.deleteLater()

        self.client.disconnect()

        # Context manager makes sure that things get cleaned up in the right order.
        with (
            self.settings.cleanup(),
            self.client_thread.stop(),
            self.notify_thread.stop(),
        ):
            pass

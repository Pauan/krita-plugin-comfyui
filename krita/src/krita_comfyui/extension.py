from krita import DockWidgetFactory, DockWidgetFactoryBase, Extension
from PyQt6.QtCore import QThread

from .server import ComfyUIClient
from .settings import Settings
from .settings.dialog import SettingsDialog
from .util.notify import NotifyWorker
from . import util


class ComfyUIExtension(Extension):
    def __init__(self, parent):
        super().__init__(parent)

        util.clear_logs()

        # The notifier needs to run async functions.
        # Instead of connecting Python's async event loop into the QEventLoop,
        # it's easier to just run it on a separate thread.
        self.thread = QThread(self)
        self.notify = NotifyWorker()
        self.notify.moveToThread(self.thread)

        self.settings = Settings(self)
        self.settings_dialog = SettingsDialog(self.settings)

        self.client = ComfyUIClient(self, self.settings, url="127.0.0.1:8188", reconnect_delay=10000)

        self.client.graph_changed.connect(self.on_graph_changed)

        notifier = parent.notifier()
        notifier.setActive(True)
        notifier.applicationClosing.connect(self.shutdown)


    def show_settings(self):
        self.settings_dialog.show()


    def createActions(self, window):
        pass


    def setup(self):
        self.thread.start()

        # We immediately connect to ComfyUI so we can update the node metadata
        self.client.connect()


    def on_graph_changed(self, graph):
        if graph.state.is_success():
            self.notify.message.emit("Job finished")

        elif graph.state.is_error():
            self.notify.message.emit("Job errored!")


    def shutdown(self):
        self.client.disconnect()
        self.thread.quit()
        self.thread.deleteLater()
        self.notify.deleteLater()
        self.settings_dialog.deleteLater()

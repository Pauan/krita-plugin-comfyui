from krita import DockWidgetFactory, DockWidgetFactoryBase, Extension

from .server import ComfyUIClient
from .settings import Settings
from . import util


class ComfyUIExtension(Extension):
    def __init__(self, parent):
        super().__init__(parent)

        util.clear_logs()

        self.client = ComfyUIClient(self, url="127.0.0.1:8188", reconnect_delay=10000)

        self.settings = Settings(self)

        notifier = parent.notifier()
        notifier.setActive(True)
        notifier.applicationClosing.connect(self.shutdown)


    def createActions(self, window):
        pass


    def setup(self):
        pass


    def shutdown(self):
        self.client.disconnect()

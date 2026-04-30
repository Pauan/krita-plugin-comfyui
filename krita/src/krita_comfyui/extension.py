from krita import DockWidgetFactory, DockWidgetFactoryBase, Extension

from .server import ComfyUIClient
from .settings import Settings
from . import util


class ComfyUIExtension(Extension):
    def __init__(self, parent):
        super().__init__(parent)

        util.clear_logs()

        self.settings = Settings(self)

        self.client = ComfyUIClient(self, self.settings, url="127.0.0.1:8188", reconnect_delay=10000)

        # We immediately connect to ComfyUI so we can update the node metadata
        self.client.connect()

        notifier = parent.notifier()
        notifier.setActive(True)
        notifier.applicationClosing.connect(self.shutdown)


    def createActions(self, window):
        pass


    def setup(self):
        pass


    def shutdown(self):
        self.client.disconnect()

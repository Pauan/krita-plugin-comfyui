from krita import DockWidgetFactory, DockWidgetFactoryBase, Extension, Krita

from .server import Server


class ComfyUIExtension(Extension):
    def __init__(self, parent):
        super().__init__(parent)

        self.server = Server()

        notifier = parent.notifier()
        notifier.setActive(True)
        notifier.applicationClosing.connect(self.shutdown)


    def createActions(self, window):
        pass


    def setup(self):
        self.server.start()


    def shutdown(self):
        self.server.stop()

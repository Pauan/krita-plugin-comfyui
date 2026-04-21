from krita import DockWidgetFactory, DockWidgetFactoryBase, Extension, Krita

from .server import Server


class ComfyUIExtension(Extension):
    def __init__(self, parent):
        super().__init__(parent)

        print("INIT")

        self.server = Server()

        print(parent is Krita.instance())

        notifier = parent.notifier()
        notifier.setActive(True)
        notifier.applicationClosing.connect(self.shutdown)


    def createActions(self, window):
        pass


    def setup(self):
        print("SETUP")

        self.server.start()

        print("SETUP DONE")


    def shutdown(self):
        print("SHUTDOWN")

        self.server.stop()

        print("SHUTDOWN DONE")

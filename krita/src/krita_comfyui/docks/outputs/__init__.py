from krita import DockWidget
from PyQt6.QtWidgets import (
    QSizePolicy,
    QWidget,
)
from ...extension import ComfyUIExtension
from ...util.krita import DocumentManager, Document, get_extension
from ...util.qt import LayoutManager
from .images import ImageWidget
from .live_mode import LiveModeWidget
from .text import TextWidget


class OutputsWidget(QWidget):
    def __init__(self, settings):
        super().__init__()

        self.settings = settings
        self.enable_live_mode = self.settings.item("enable_live_mode")

        self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred))

        self.document = DocumentManager(self)
        self.layout = LayoutManager(self)

        with self.layout.column() as column:
            self.text = TextWidget(self.document)
            column.widget(self.text)

            with column.stack(stretch=1) as stack:
                self.stack = stack

                self.image = ImageWidget(self.document)
                stack.widget(self.image)

                self.live_mode = LiveModeWidget(self.document)
                stack.widget(self.live_mode)

        # TODO remove the event listener when the QWidget is destroyed
        self.enable_live_mode.with_value(self.on_live_mode_changed)


    def on_live_mode_changed(self, live_mode):
        if live_mode:
            self.stack.set_current_index(1)
        else:
            self.stack.set_current_index(0)


    def set_text(self, document, text):
        self.text.set_text(document, text)


    def new_images(self, document, images):
        if len(images) > 0:
            if self.enable_live_mode.get():
                self.live_mode.new_images(document, images)
            else:
                self.image.new_images(document, images)


class ComfyUIOutputWidget(DockWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ComfyUI Outputs")

        self.extension = get_extension(ComfyUIExtension)
        self.extension.client.graph_changed.connect(self.on_graph_changed)

        self._widget = OutputsWidget(self.extension.settings.settings)
        self._widget.setParent(self)
        self._widget.image.storage.total_bytes_changed.connect(self.update_title)
        self.setWidget(self._widget)

        self.update_title()


    def update_title(self):
        bytes = self._widget.image.storage.total_bytes

        if bytes == 0:
            self.setWindowTitle("ComfyUI Outputs")

        else:
            bytes = float(bytes)
            suffix = "bytes"

            if bytes >= 1024.0:
                bytes = bytes / 1024.0
                suffix = "KB"

            if bytes >= 1024.0:
                bytes = bytes / 1024.0
                suffix = "MB"

            if bytes >= 1024.0:
                bytes = bytes / 1024.0
                suffix = "GB"

            bytes = round(bytes, 2)

            self.setWindowTitle(f"ComfyUI Outputs  ({bytes:g} {suffix})")


    def canvasChanged(self, canvas):
        self._widget.document.check_changes()


    def on_graph_changed(self, info):
        if info.state.is_success():
            images = {}
            texts = []

            for output in info.outputs:
                if "krita_comfyui_output_images" in output:
                    # Organizes the images into batches based on the order
                    for image in output["krita_comfyui_output_images"]:
                        order = image["order"]
                        batch = images.get(order, None)
                        if batch is None:
                            batch = []
                            images[order] = batch
                        batch.append(image)

                if "krita_comfyui_text" in output:
                    texts.extend(output["krita_comfyui_text"])

            # Sort text by order and name
            texts.sort(key=lambda x: (x["order"], x["name"].casefold()))

            # The image group is sorted by the order.
            images = [batch for order, batch in sorted(images.items(), key=lambda x: x[0])]

            for document in Document.all():
                if document.root_layer().id == info.document_id:
                    self._widget.new_images(document, images)
                    self._widget.set_text(document, texts)

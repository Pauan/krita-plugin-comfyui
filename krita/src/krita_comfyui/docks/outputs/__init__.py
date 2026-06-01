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
    def __init__(self, extension, settings):
        super().__init__()

        self.extension = extension
        self.extension.job_started.connect(self.on_job_started)

        self.settings = settings

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

                self.live_mode = LiveModeWidget(extension, self.document)
                stack.widget(self.live_mode)

        self.live_mode_enabled = self.settings.with_selected_workflow(lambda x: x.value("live_mode_enabled", bool))
        self.live_mode_enabled.with_value(self.on_live_mode_changed)


    def on_live_mode_changed(self, live_mode):
        if live_mode:
            self.live_mode.update_preview()
            self.stack.set_current_index(1)
        else:
            self.image.update_preview()
            self.stack.set_current_index(0)


    def on_job_started(self):
        if self.live_mode_enabled.get():
            self.live_mode.job_started()
        else:
            self.image.job_started()


    def get_title(self):
        bytes = self.live_mode.total_bytes + self.image.total_bytes

        if bytes == 0:
            return "ComfyUI Outputs"

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

            return f"ComfyUI Outputs  ({bytes:g} {suffix})"


    def set_text(self, document, text, is_live_mode):
        if is_live_mode:
            with self.extension.disable_live_mode(), document.disable_modification():
                self.text.set_text(document, text)
        else:
            self.text.set_text(document, text)


    def new_images(self, document, images, is_live_mode):
        if len(images) > 0:
            if is_live_mode:
                self.live_mode.new_images(document, images, self.live_mode_enabled.get())
            else:
                self.image.new_images(document, images)


class ComfyUIOutputWidget(DockWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ComfyUI Outputs")

        self.extension = get_extension(ComfyUIExtension)
        self.extension.client.graph_changed.connect(self.on_graph_changed)

        self._widget = OutputsWidget(self.extension, self.extension.settings)
        self._widget.setParent(self)
        self._widget.image.total_bytes_changed.connect(self.update_title)
        self._widget.live_mode.total_bytes_changed.connect(self.update_title)
        self.setWidget(self._widget)

        self.update_title()


    def update_title(self):
        self.setWindowTitle(self._widget.get_title())


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
                        image["duration"] = info.duration
                        image["timestamp"] = info.timestamp

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
                    self._widget.new_images(document, images, info.is_live_mode)
                    self._widget.set_text(document, texts, info.is_live_mode)

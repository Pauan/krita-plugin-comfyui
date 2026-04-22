import krita
from krita import DockWidget
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from .layer import (Document, Layer, Image)


class OutputsWidget(QListWidget):
    image_selected = pyqtSignal(QListWidgetItem)

    image_size = 96

    def __init__(self, parent: QWidget | None):
        super().__init__(parent)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setIconSize(QSize(self.image_size, self.image_size))
        self.setFrameStyle(QFrame.Shape.NoFrame)
        #self.setStyleSheet(self._list_css)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(False)

        #self.itemClicked.connect(self.image_clicked)
        #self.itemDoubleClicked.connect(self.item_activated)

        self.itemSelectionChanged.connect(self.item_selected)


    def apply_image(self, document, image):
        activeLayer = document.active_layer()
        parent = activeLayer.parent

        layer = Layer.fromImage(document, image["name"], image["image"], image["x"], image["y"])

        parent.insert_child(layer, activeLayer)


    def show_preview(self, image):
        document = Document.current()

        if document is not None:
            name = "[Preview] ComfyUI"

            preview_layer = document.make_preview_layer(name)

            preview_layer.replace_image(image["image"], image["x"], image["y"])

            preview_layer.name = name
            preview_layer.is_visible = True
            preview_layer.is_locked = True
            preview_layer.move_to_top(document.root_layer())


    def hide_preview(self):
        document = Document.current()

        if document is not None:
            preview_layer = document.find_preview_layer()

            if preview_layer is not None:
                preview_layer.is_visible = False


    def delete_preview(self):
        document = Document.current()

        if document is not None:
            document.remove_preview_layer()


    def selected_images(self):
        selected = []

        for item in self.selectedItems():
            data = item.data(Qt.ItemDataRole.UserRole)

            if data is not None:
                selected.append(data)

        return selected


    def item_selected(self):
        selected = self.selected_images()

        if len(selected) > 0:
            self.show_preview(selected[-1])
        else:
            self.hide_preview()


    def apply_selected(self):
        self.delete_preview()

        document = Document.current()

        if document is not None:
            for image in self.selected_images():
                self.apply_image(document, image)


    def add_outputs(self, outputs: list):
        if len(outputs) > 0:
            if len(outputs) > 1:
                header = QListWidgetItem("")
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                header.setData(Qt.ItemDataRole.UserRole, None)
                #header.setData(Qt.ItemDataRole.ToolTipRole, job.params.prompt)
                header.setSizeHint(QSize(9999, 10))
                header.setTextAlignment(Qt.AlignmentFlag.AlignLeft)
                self.addItem(header)

            for output in outputs:
                image = Image.from_base64(output["png"], "png")

                # Displays the image at twice the image_size resolution then downscales it
                thumbnail = image.scale_to_fit(self.image_size * 2, self.image_size * 2)

                tooltip = output["name"]

                item = QListWidgetItem(thumbnail.to_icon(), "")

                item.setData(Qt.ItemDataRole.UserRole, {
                    "image": image,
                    "x": output["x"],
                    "y": output["y"],
                    "name": output["name"],
                })

                item.setData(Qt.ItemDataRole.ToolTipRole, tooltip)

                self.addItem(item)

            self.scrollToBottom()


class ComfyUIOutputWidget(DockWidget):
    images = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ComfyUI Outputs")

        self.images.connect(self.add_images)

        self._outputs = OutputsWidget(self)

        self.setWidget(self._outputs)

        #self._frame = QStackedWidget(self)
        #self._frame.addWidget(self._welcome)
        #self._frame.addWidget(self._generation)
        #self._frame.addWidget(self._upscaling)
        #self._frame.addWidget(self._live)
        #self._frame.addWidget(self._animation)
        #self._frame.addWidget(self._custom)
        #self._frame.addWidget(self._custom_placeholder)
        #self.setWidget(self._frame)

    def canvasChanged(self, canvas: krita.Canvas):
        if canvas is not None and canvas.view() is not None:
            pass

    def add_images(self, images):
        self._outputs.add_outputs(images)

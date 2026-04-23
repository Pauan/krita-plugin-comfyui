import krita
from krita import DockWidget
from PyQt6.QtCore import QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
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
from .layer import (Document, Layer, Image, Bounds)


class OutputsWidget(QListWidget):
    image_selected = pyqtSignal(QListWidgetItem)

    image_size = 96
    image_padding = 1
    spacer_height = 2

    def __init__(self, parent: QWidget | None):
        super().__init__(parent)

        self.old_selected = None

        self.image_menus = []

        self.menu = QMenu(self)
        #self.image_menus.append(self.menu.addSection("Apply images to..."))
        self.image_menus.append(self.menu.addAction(Krita.icon("cloneLayer"), "New layer", self.apply_new_layer))
        self.image_menus.append(self.menu.addAction(Krita.icon("window-new"), "New document", self.apply_new_document))
        self.image_menus.append(self.menu.addAction(Krita.icon("paintLayer"), "Existing layer", self.apply_existing_layer))
        self.menu.addSeparator()
        self.image_menus.append(self.menu.addAction(Krita.icon("edit-clear"), "Delete selected", self.delete_selected))
        self.menu.addAction(Krita.icon("deletelayer"), "Delete all", self.delete_all)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setIconSize(QSize(self.image_size, self.image_size))
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(False)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.itemActivated.connect(self.item_activated)
        self.itemDoubleClicked.connect(self.item_double_clicked)
        self.itemSelectionChanged.connect(self.selection_changed)


    def thumbnail(self, image, applied):
        # Displays the image at twice the image_size resolution then downscales it
        thumbnail = image.scale_to_fit(self.image_size * 2, self.image_size * 2)

        if applied:
            thumbnail.draw_icon(
                QIcon(Image.filename("diamond.svg")),
                Bounds(6, 6, 38, 38),
                alignment=Qt.AlignmentFlag.AlignCenter,
                state=QIcon.State.On,
            )

        return thumbnail.to_icon()


    def apply_image(self, document, image):
        activeLayer = document.active_layer()
        parent = activeLayer.parent

        layer = Layer.fromImage(document, image["name"], image["image"], image["x"], image["y"])

        parent.insert_child(layer, activeLayer)


    def show_preview(self, image):
        document = Document.current()

        if document is not None:
            document.show_preview_layer(
                name="[Preview] ComfyUI",
                image=image["image"],
                x=image["x"],
                y=image["y"],
            )


    def hide_preview(self):
        document = Document.current()

        if document is not None:
            document.hide_preview_layer()


    def delete_preview(self):
        document = Document.current()

        if document is not None:
            document.remove_preview_layer()


    def selected_images(self):
        selected = []

        for item in self.selectedItems():
            data = item.data(Qt.ItemDataRole.UserRole)

            if data is not None:
                selected.append((item, data))

        return selected


    def item_activated(self, item):
        if item.isSelected():
            if self.old_selected is item:
                self.old_selected = None
                item.setSelected(False)

            else:
                self.old_selected = item

        else:
            self.old_selected = None


    def item_double_clicked(self, item):
        if item.isSelected():
            self.old_selected = None
            item.setSelected(False)

        else:
            self.old_selected = item
            item.setSelected(True)


    def selection_changed(self):
        selected = self.selected_images()

        if len(selected) > 0:
            self.show_preview(selected[-1][1])
        else:
            self.old_selected = None
            self.hide_preview()


    def apply_new_layer(self):
        self.delete_preview()

        document = Document.current()

        if document is not None:
            for (item, image) in self.selected_images():
                item.setIcon(self.thumbnail(image["image"], True))

                self.apply_image(document, image)


    def apply_new_document(self):
        pass

    def apply_existing_layer(self):
        pass

    def delete_selected(self):
        pass


    def delete_all(self):
        reply = QMessageBox.question(
            self,
            "Delete all",
            "Are you sure you want to delete all ComfyUI output images?",
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.delete_preview()
            self.clear()


    def add_outputs(self, outputs: list):
        if len(outputs) > 0:
            # When there are existing items, and it is a batch of multiple images,
            # add a spacer, which causes the new items to be put onto a new row.
            if len(outputs) > 1 and self.count() > 0:
                header = QListWidgetItem("")
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                header.setData(Qt.ItemDataRole.UserRole, None)
                header.setSizeHint(QSize(9999, self.spacer_height))
                header.setTextAlignment(Qt.AlignmentFlag.AlignLeft)
                self.addItem(header)

            for output in outputs:
                tooltip = output["name"]

                image = Image.from_base64(output["png"], "png")

                item = QListWidgetItem(self.thumbnail(image, applied=False), None)

                item.setSizeHint(QSize(self.image_size + (self.image_padding * 2), self.image_size + (self.image_padding * 2)))

                item.setData(Qt.ItemDataRole.UserRole, {
                    "image": image,
                    "x": output["x"],
                    "y": output["y"],
                    "name": output["name"],
                })

                item.setData(Qt.ItemDataRole.ToolTipRole, tooltip)

                self.addItem(item)

            self.scrollToBottom()


    def show_context_menu(self, pos: QPoint):
        images_selected = len(self.selected_images()) > 0

        for menu in self.image_menus:
            menu.setEnabled(images_selected)

        self.menu.exec(self.mapToGlobal(pos))


class ComfyUIOutputWidget(DockWidget):
    images = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ComfyUI Outputs")

        self.images.connect(self.add_images)

        self._outputs = OutputsWidget(self)

        self.setWidget(self._outputs)

    def canvasChanged(self, canvas: krita.Canvas):
        if canvas is not None and canvas.view() is not None:
            pass

    def add_images(self, images):
        self._outputs.add_outputs(images)

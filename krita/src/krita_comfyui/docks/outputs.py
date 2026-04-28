from krita import DockWidget
from PyQt6.QtCore import QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QToolButton,
    QWidget,
)
from ..extension import ComfyUIExtension
from ..krita import Document, Layer, Image, Bounds, BlockSignals, get_extension


class OutputsWidget(QListWidget):
    image_selected = pyqtSignal(QListWidgetItem)

    image_size = 96
    image_padding = 1
    spacer_height = 2

    def __init__(self, parent: QWidget | None):
        super().__init__(parent)

        self.old_selected = None

        self.image_menus = []
        self.all_menus = []

        self.menu = QMenu(self)
        #self.image_menus.append(self.menu.addSection("Apply images to..."))
        self.image_menus.append(self.menu.addAction(Krita.icon("cloneLayer"), "New layer", self.apply_new_layer))
        self.image_menus.append(self.menu.addAction(Krita.icon("window-new"), "New document", self.apply_new_document))
        self.image_menus.append(self.menu.addAction(Krita.icon("paintLayer"), "Existing layer", self.apply_existing_layer))
        self.menu.addSeparator()
        self.image_menus.append(self.menu.addAction(Krita.icon("edit-clear"), "Delete selected", self.delete_selected))
        self.all_menus.append(self.menu.addAction(Krita.icon("deletelayer"), "Delete all", self.delete_all))

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


    def apply_selected_images(self):
        with BlockSignals(self):
            self.old_selected = None
            self.delete_preview()

            for (item, image) in self.selected_images():
                item.setSelected(False)
                item.setIcon(self.thumbnail(image["image"], True))
                yield image


    def apply_new_layer(self):
        document = Document.current()

        if document is not None:
            for image in self.apply_selected_images():
                self.apply_image(document, image)


    def apply_existing_layer(self):
        document = Document.current()

        if document is not None:
            activeLayer = document.active_layer()

            for image in self.apply_selected_images():
                activeLayer.write_image(image["image"], image["x"], image["y"])

            document.refresh()


    def apply_new_document(self):
        resolution = 300.0
        profile = ""

        document = Document.current()

        if document is not None:
            resolution = document.pixels_per_inch()
            profile = document.color_profile()

        for image in self.apply_selected_images():
            new_document = Document.create(
                image["image"].width,
                image["image"].height,
                image["name"],
                "RGBA",
                "U8",
                profile,
                resolution,
            )

            for layer in new_document.root_layer().all_children():
                layer.remove()

            layer = Layer.fromImage(new_document, image["name"], image["image"], 0, 0)

            new_document.root_layer().insert_child(layer, None)


    def delete_selected(self):
        with BlockSignals(self):
            self.old_selected = None

            seen_item = False

            for i in reversed(range(self.count())):
                item = self.item(i)

                if item.isSelected():
                    self.takeItem(i)

                else:
                    data = item.data(Qt.ItemDataRole.UserRole)

                    if data is None:
                        # Remove unneeded spacers
                        if not seen_item:
                            self.takeItem(i)
                        seen_item = False
                    else:
                        seen_item = True

            if self.count() == 0:
                self.delete_preview()
            else:
                self.hide_preview()


    def delete_all(self):
        reply = QMessageBox.question(
            self,
            "Delete all",
            "Are you sure you want to delete all ComfyUI output images?",
        )

        if reply == QMessageBox.StandardButton.Yes:
            with BlockSignals(self):
                self.old_selected = None
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

        has_images = self.count() > 0

        for menu in self.image_menus:
            menu.setEnabled(images_selected)

        for menu in self.all_menus:
            menu.setEnabled(has_images)

        self.menu.exec(self.mapToGlobal(pos))


class ComfyUIOutputWidget(DockWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ComfyUI Outputs")

        self.extension = get_extension(ComfyUIExtension)
        self.extension.client.graph_changed.connect(self.on_graph_changed)

        self._outputs = OutputsWidget(self)

        self.setWidget(self._outputs)

    def canvasChanged(self, canvas):
        pass

    def on_graph_changed(self, info):
        if info.state.is_ended():
            for output in info.outputs:
                if output.node_name == "krita_comfyui: KritaOutput":
                    images = output.value["krita_comfyui_output_images"]
                    self.add_images(images)

    def add_images(self, images):
        self._outputs.add_outputs(images)

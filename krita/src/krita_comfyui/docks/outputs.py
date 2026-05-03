from uuid import uuid4
from krita import DockWidget
from PyQt6.QtCore import QObject, QPoint, QSize, Qt, pyqtSignal
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
    QWidget,
)
from ..extension import ComfyUIExtension
from ..util.krita import DocumentManager, Document, Layer, Image, Bounds, get_extension
from ..util.qt import LayoutManager, BlockSignals


# Deletes elements from the list which the function returns True
def delete_all(list, f):
    indexes = []

    for index in reversed(range(len(list))):
        if f(list[index]):
            indexes.append(index)

    for index in indexes:
        del list[index]


class ImageStorage(QObject):
    def __init__(self, parent, thumbnail_size):
        super().__init__(parent)

        self.thumbnail_size = thumbnail_size
        self.images = {}
        self.metadata = {}
        self.uuids = []


    def save_uuids(self, document):
        if len(self.uuids) == 0:
            document.remove_key("krita_comfyui/image_uuids")
        else:
            document.set_key_json("krita_comfyui/image_uuids", "krita_comfyui: Image UUIDs", self.uuids)


    def load_uuid(self, document, uuid):
        assert not uuid in self.images
        assert not uuid in self.metadata

        metadata = document.get_key_json(f"krita_comfyui/image_metadata/{uuid}", None)
        bytes = document.get_key_bytes(f"krita_comfyui/image_bytes/{uuid}", None)

        if metadata is None or bytes is None:
            self.images[uuid] = Image.from_qicon(
                Krita.icon("window-close"),
                width=self.thumbnail_size,
                height=self.thumbnail_size,
            )

            self.metadata[uuid] = {
                "width": self.thumbnail_size,
                "height": self.thumbnail_size,
                "x": 0,
                "y": 0,
                "name": "[ERROR]",
            }

        else:
            self.images[uuid] = Image.from_packed_bytes(bytes, metadata["width"], metadata["height"], swap_rgb=False)
            self.metadata[uuid] = metadata


    # TODO use document.all_keys() to verify that there aren't any dangling leftover keys
    def load_all(self, document):
        self.images = {}
        self.metadata = {}
        self.uuids = []

        if document is not None:
            self.uuids = document.get_key_json("krita_comfyui/image_uuids", [])

            for batch in self.uuids:
                for uuid in batch:
                    self.load_uuid(document, uuid)

        for batch in self.uuids:
            yield [self.lookup_uuid(uuid) for uuid in batch]


    def lookup_uuid(self, uuid):
        metadata = self.metadata[uuid]

        return {
            "uuid": uuid,
            "image": self.images[uuid],
            "x": metadata["x"],
            "y": metadata["y"],
            "name": metadata["name"],
            "applied": metadata.get("applied", False),
            "selected": metadata.get("selected", False),
        }


    def delete_uuid(self, document, uuid):
        try:
            del self.images[uuid]
        except KeyError:
            pass

        try:
            del self.metadata[uuid]
        except KeyError:
            pass

        try:
            document.remove_key(f"krita_comfyui/image_bytes/{uuid}")
        finally:
            document.remove_key(f"krita_comfyui/image_metadata/{uuid}")


    def save(self, document, info):
        uuid = str(uuid4())

        image = Image.from_base64(info["bytes"], info["width"], info["height"])
        bytes = image.bytes()

        metadata = {
            "width": info["width"],
            "height": info["height"],
            "x": info["x"],
            "y": info["y"],
            "name": info["name"],
        }

        assert not uuid in self.images
        assert not uuid in self.metadata

        try:
            self.images[uuid] = image
            self.metadata[uuid] = metadata

            document.set_key_bytes(f"krita_comfyui/image_bytes/{uuid}", "krita_comfyui: Image Bytes", bytes)
            document.set_key_json(f"krita_comfyui/image_metadata/{uuid}", "krita_comfyui: Image Metadata", metadata)

        # If something goes wrong, make absolutely sure that we clean up
        except:
            self.delete_uuid(document, uuid)
            raise

        return uuid


    def set_metadata(self, document, uuid, key: str, value: bool):
        metadata = self.metadata[uuid]

        old_value = metadata.get(key, False)

        if old_value != value:
            if value:
                metadata[key] = value

            else:
                try:
                    del metadata[key]
                except KeyError:
                    pass

            document.set_key_json(f"krita_comfyui/image_metadata/{uuid}", "krita_comfyui: Image Metadata", metadata)


    def set_applied(self, document, uuid, applied):
        self.set_metadata(document, uuid, "applied", applied)

    def set_selected(self, document, uuid, selected):
        self.set_metadata(document, uuid, "selected", selected)


    def save_batch(self, document, batch):
        uuids = [self.save(document, info) for info in batch]

        if len(uuids) > 0:
            self.uuids.append(uuids)
            self.save_uuids(document)

        return [self.lookup_uuid(uuid) for uuid in uuids]


    def clear(self, document):
        for batch in self.uuids:
            for uuid in batch:
                self.delete_uuid(document, uuid)

        document.remove_key("krita_comfyui/image_uuids")

        self.images = {}
        self.metadata = {}
        self.uuids = []


    def remove(self, document, uuids):
        for uuid in uuids:
            self.delete_uuid(document, uuid)

        def remove_batch(batch):
            delete_all(batch, lambda uuid: uuid in uuids)
            return len(batch) == 0

        delete_all(self.uuids, remove_batch)

        self.save_uuids(document)


class TextWidget(QWidget):
    def __init__(self, document):
        super().__init__()

        self.document = document
        self.document.document_changed.connect(self.load_texts)

        self.layout = LayoutManager(self)

        with self.layout.column() as column:
            with column.scroll(max_height=200) as scroll:
                widget = QWidget()
                layout = LayoutManager(widget)

                with layout.column() as column:
                    self.column = column

                scroll.setWidget(widget)

        self.load_texts()


    def load_texts(self):
        document = self.document.current()

        if document is not None:
            texts = document.get_key_json("krita_comfyui/output_texts", [])
        else:
            texts = []

        self.display_text(texts)


    def display_text(self, texts):
        self.column.clear()

        if len(texts) == 0:
            self.setVisible(False)

        else:
            for text in texts:
                with self.column.group(title=text["name"]) as group:
                    layout = LayoutManager(group)

                    with layout.column() as column:
                        column.set_padding(left=8, right=8, bottom=6)
                        column.label(text=text["text"], selectable=True)

            self.setVisible(True)


    def set_text(self, texts):
        document = self.document.current()

        if document is not None:
            if len(texts) == 0:
                document.remove_key("krita_comfyui/output_texts")
            else:
                document.set_key_json("krita_comfyui/output_texts", "krita_comfyui: Output Texts", texts)

        self.display_text(texts)


class ImageWidget(QListWidget):
    image_selected = pyqtSignal(QListWidgetItem)

    image_size = 96
    image_padding = 1
    spacer_height = 2

    def __init__(self, document):
        super().__init__()

        self.document = document
        self.document.document_changed.connect(self.load_document)

        # Displays the thumbnails at twice the image_size resolution then downscales it
        self.thumbnail_size = self.image_size * 2

        self.storage = ImageStorage(self, self.thumbnail_size)

        self.selected = []

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

        self.itemPressed.connect(self.item_clicked, type=Qt.ConnectionType.DirectConnection)
        self.itemDoubleClicked.connect(self.item_double_clicked, type=Qt.ConnectionType.DirectConnection)
        # This forces itemSelectionChanged to trigger after itemPressed
        self.itemSelectionChanged.connect(self.selection_changed, type=Qt.ConnectionType.QueuedConnection)

        self.load_document()


    def load_document(self):
        with BlockSignals(self):
            self.selected = []
            self.clear()

            for batch in self.storage.load_all(self.document.current()):
                self.add_images(batch, allow_selection=True)


    def thumbnail(self, image, applied):
        thumbnail = image.scale_to_fit(self.thumbnail_size, self.thumbnail_size)

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
        document = self.document.current()

        if document is not None:
            document.show_preview_layer(
                name="[Preview] ComfyUI",
                image=image["image"],
                x=image["x"],
                y=image["y"],
            )


    def hide_preview(self):
        document = self.document.current()

        if document is not None:
            document.hide_preview_layer()


    def delete_preview(self):
        document = self.document.current()

        if document is not None:
            document.remove_preview_layer()


    def selected_images(self):
        selected = []

        for item in self.selectedItems():
            data = item.data(Qt.ItemDataRole.UserRole)

            if data is not None:
                selected.append((item, data))

        return selected


    def item_clicked(self, item):
        if item.isSelected() and len(self.selected) == 1 and self.selected[0] is item:
            self.selected = []
            item.setSelected(False)


    def item_double_clicked(self, item):
        if item.isSelected():
            self.selected = []
            item.setSelected(False)

        else:
            self.selected = [item]
            item.setSelected(True)


    def update_selected_state(self):
        document = self.document.current()

        if document is not None:
            for i in range(self.count()):
                item = self.item(i)
                data = item.data(Qt.ItemDataRole.UserRole)

                if data is not None:
                    self.storage.set_selected(document, data["uuid"], item.isSelected())


    def selection_changed(self):
        self.update_selected_state()

        selected = self.selected_images()

        self.selected = [item for (item, _) in selected]

        if len(selected) > 0:
            # Show a preview of the last selected image
            self.show_preview(selected[-1][1])

        else:
            self.hide_preview()


    def apply_selected_images(self, document):
        with BlockSignals(self):
            self.selected = []
            self.delete_preview()

            for (item, image) in self.selected_images():
                self.storage.set_applied(document, image["uuid"], True)

                item.setSelected(False)
                item.setIcon(self.thumbnail(image["image"], True))
                yield image

            self.update_selected_state()


    def apply_new_layer(self):
        document = self.document.current()

        if document is not None:
            for image in self.apply_selected_images(document):
                self.apply_image(document, image)


    def apply_existing_layer(self):
        document = self.document.current()

        if document is not None:
            activeLayer = document.active_layer()

            for image in self.apply_selected_images(document):
                activeLayer.write_image(image["image"], image["x"], image["y"])

            document.refresh()


    def apply_new_document(self):
        document = self.document.current()

        if document is not None:
            resolution = document.pixels_per_inch()
            profile = document.color_profile()

            for image in self.apply_selected_images(document):
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
            self.selected = []

            uuids = []

            seen_item = False

            for i in reversed(range(self.count())):
                item = self.item(i)

                data = item.data(Qt.ItemDataRole.UserRole)

                if item.isSelected():
                    if data is not None:
                        uuids.append(data["uuid"])

                    self.takeItem(i)

                else:
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

            document = self.document.current()
            if document is not None:
                self.storage.remove(document, uuids)


    # Returns true if the previous images were in a batch
    def is_previous_batch(self):
        for i in reversed(range(self.count())):
            item = self.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)

            # We found a spacer, so stop searching
            if data is None:
                return False
            else:
                return data["is_batch"]

        return False


    def delete_all(self):
        reply = QMessageBox.question(
            self,
            "Delete all",
            "Are you sure you want to delete all ComfyUI output images?",
        )

        if reply == QMessageBox.StandardButton.Yes:
            with BlockSignals(self):
                document = self.document.current()
                if document is not None:
                    self.storage.clear(document)

                self.selected = []
                self.delete_preview()
                self.clear()


    def add_images(self, images, allow_selection):
        with BlockSignals(self):
            if len(images) > 0:
                # This is a batch of multiple images.
                is_batch = len(images) > 1

                # There are two situations where we add a spacer:
                #   1. If we are a batch and there are existing items.
                #   2. If we are not a batch but the previous items are in a batch.
                if is_batch:
                    should_add_spacer = self.count() > 0
                else:
                    should_add_spacer = self.is_previous_batch()

                if should_add_spacer:
                    header = QListWidgetItem("")
                    header.setFlags(Qt.ItemFlag.NoItemFlags)
                    header.setData(Qt.ItemDataRole.UserRole, None)
                    header.setSizeHint(QSize(9999, self.spacer_height))
                    header.setTextAlignment(Qt.AlignmentFlag.AlignLeft)
                    self.addItem(header)

                for info in images:
                    tooltip = info["name"]

                    item = QListWidgetItem(self.thumbnail(info["image"], applied=info["applied"]), None)

                    item.setSizeHint(QSize(self.image_size + (self.image_padding * 2), self.image_size + (self.image_padding * 2)))

                    item.setData(Qt.ItemDataRole.UserRole, {
                        "uuid": info["uuid"],
                        "image": info["image"],
                        "x": info["x"],
                        "y": info["y"],
                        "name": info["name"],
                        "is_batch": is_batch,
                    })

                    item.setData(Qt.ItemDataRole.ToolTipRole, tooltip)

                    self.addItem(item)

                    if info["selected"]:
                        assert allow_selection
                        item.setSelected(True)
                        self.selected.append(item)

                self.scrollToBottom()


    def new_images(self, images):
        document = self.document.current()

        if document is not None:
            images = self.storage.save_batch(document, images)
            self.add_images(images, allow_selection=False)


    def show_context_menu(self, pos: QPoint):
        images_selected = len(self.selected_images()) > 0

        has_images = self.count() > 0

        for menu in self.image_menus:
            menu.setEnabled(images_selected)

        for menu in self.all_menus:
            menu.setEnabled(has_images)

        self.menu.exec(self.mapToGlobal(pos))


class OutputsWidget(QWidget):
    def __init__(self):
        super().__init__()

        self.document = DocumentManager(self)
        self.layout = LayoutManager(self)

        with self.layout.column() as column:
            self.text = TextWidget(self.document)
            column.widget(self.text)

            self.image = ImageWidget(self.document)
            column.widget(self.image, stretch=1)


class ComfyUIOutputWidget(DockWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ComfyUI Outputs")

        self.extension = get_extension(ComfyUIExtension)
        self.extension.client.graph_changed.connect(self.on_graph_changed)

        self._widget = OutputsWidget()
        self._widget.setParent(self)
        self.setWidget(self._widget)


    def canvasChanged(self, canvas):
        self._widget.document.check_changes()


    def on_graph_changed(self, info):
        if info.state.is_success():
            images = []
            texts = []

            for output in info.outputs:
                if output.node_name == "krita_comfyui: KritaOutput":
                    images.append(output.value["krita_comfyui_output_images"])

                elif output.node_name == "krita_comfyui: KritaText":
                    texts.extend(output.value["krita_comfyui_text"])

            # Sorts the bigger batches first
            images.sort(key=lambda x: len(x), reverse=True)
            texts.sort(key=lambda x: x["name"].casefold())

            for batch in images:
                self.add_images(batch)

            self.set_text(texts)


    def set_text(self, texts):
        self._widget.text.set_text(texts)

    def add_images(self, images):
        self._widget.image.new_images(images)

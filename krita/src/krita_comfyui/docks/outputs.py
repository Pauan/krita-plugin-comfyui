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
    total_bytes_changed = pyqtSignal()

    def __init__(self, parent, thumbnail_size):
        super().__init__(parent)

        self.thumbnail_size = thumbnail_size
        self.images = {}
        self.metadata = {}
        self.uuids = []
        self.total_bytes = 0


    def all_uuids(self):
        for group in self.uuids:
            for batch in group:
                yield from batch


    # Verifies that there aren't any dangling leftover images in the document.
    def verify_storage_integrity(self, document):
        seen_uuid = set()

        for uuid in self.all_uuids():
            seen_uuid.add(uuid)

        for key in document.all_keys():
            uuid = key.removeprefix("krita_comfyui/image_metadata/")
            if uuid != key:
                assert uuid in seen_uuid

            uuid = key.removeprefix("krita_comfyui/image_bytes/")
            if uuid != key:
                assert uuid in seen_uuid


    def save_uuids(self, document):
        if len(self.uuids) == 0:
            document.remove_key("krita_comfyui/image_uuids")
        else:
            document.set_key_json("krita_comfyui/image_uuids", "krita_comfyui: Image UUIDs", self.uuids)

        self.verify_storage_integrity(document)


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
                "format": "rgba",
                "width": self.thumbnail_size,
                "height": self.thumbnail_size,
                "x": 0,
                "y": 0,
                "name": "[ERROR]",
            }

        else:
            image = Image.from_packed_bytes(bytes, metadata["width"], metadata["height"], swap_rgb=False)
            self.total_bytes += image.byte_size()
            self.images[uuid] = image
            self.metadata[uuid] = metadata


    # Migrates from the old format where groups weren't saved.
    def migrate_uuids(self, uuids):
        output = []

        for group in uuids:
            # It's an old style batch, so we wrap it into a group.
            if len(group) > 0 and isinstance(group[0], str):
                output.append([group])
            else:
                output.append(group)

        return output


    def load_all(self, document):
        self.images = {}
        self.metadata = {}
        self.uuids = []
        self.total_bytes = 0

        if document is not None:
            self.uuids = self.migrate_uuids(document.get_key_json("krita_comfyui/image_uuids", []))

            for uuid in self.all_uuids():
                self.load_uuid(document, uuid)

            self.verify_storage_integrity(document)

        self.total_bytes_changed.emit()

        return [[[self.lookup_uuid(uuid) for uuid in batch] for batch in group] for group in self.uuids]


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
            image = self.images[uuid]
            self.total_bytes -= image.byte_size()
        except KeyError:
            pass

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

        self.total_bytes += image.byte_size()

        metadata = {
            "format": "rgba",
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


    def save_group(self, document, group):
        group = [[self.save(document, info) for info in batch] for batch in group]

        self.total_bytes_changed.emit()

        assert len(group) > 0

        self.uuids.append(group)
        self.save_uuids(document)

        return [[self.lookup_uuid(uuid) for uuid in batch] for batch in group]


    def clear(self, document):
        for uuid in self.all_uuids():
            self.delete_uuid(document, uuid)

        document.remove_key("krita_comfyui/image_uuids")

        self.images = {}
        self.metadata = {}
        self.uuids = []
        self.total_bytes = 0

        self.verify_storage_integrity(document)

        self.total_bytes_changed.emit()


    def remove(self, document, uuids):
        for uuid in uuids:
            self.delete_uuid(document, uuid)

        self.total_bytes_changed.emit()

        def remove_batch(batch):
            delete_all(batch, lambda uuid: uuid in uuids)
            return len(batch) == 0

        def remove_group(group):
            delete_all(group, remove_batch)
            return len(group) == 0

        delete_all(self.uuids, remove_group)

        self.save_uuids(document)


class TextWidget(QWidget):
    def __init__(self, document):
        super().__init__()

        self.document = document
        self.document.document_changed.connect(self.load_texts)

        self.texts = []

        self.text_menus = []

        self.menu = QMenu(self)
        self.text_menus.append(self.menu.addAction(Krita.icon("deletelayer"), "Delete all texts", self.clear_text))

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self.layout = LayoutManager(self)

        self.setStyleSheet("""
            QGroupBox {
                text-decoration: underline;
                font-weight: bold;
            }

            QGroupBox::title {
                subcontrol-position: top left;
                subcontrol-origin: border;
                margin-left: 8px;
                margin-top: 6px;
            }
        """)

        with self.layout.column() as column:
            with column.scroll(max_height=200) as scroll:
                widget = QWidget()
                layout = LayoutManager(widget)

                with layout.column() as column:
                    self.column = column

                scroll.setWidget(widget)

        self.load_texts()


    def show_context_menu(self, pos: QPoint):
        has_text = len(self.texts) > 0

        for menu in self.text_menus:
            menu.setEnabled(has_text)

        self.menu.exec(self.mapToGlobal(pos))


    def load_texts(self):
        document = self.document.current()

        if document is not None:
            texts = document.get_key_json("krita_comfyui/output_texts", [])
        else:
            texts = []

        self.display_text(texts)


    def display_text(self, texts):
        self.texts = texts

        self.column.clear()

        if len(texts) == 0:
            self.setVisible(False)

        else:
            for text in texts:
                with self.column.group(title=text["name"]) as group:
                    layout = LayoutManager(group)

                    with layout.column() as column:
                        column.set_padding(left=8, right=8, bottom=6)

                        with column.label(text=text["text"], selectable=True) as label:
                            label.setWordWrap(True)

            self.setVisible(True)


    def clear_text(self):
        reply = QMessageBox.question(
            self,
            "Delete all",
            "Are you sure you want to delete all output texts?",
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.set_text([])


    def set_text(self, texts):
        document = self.document.current()

        if document is not None:
            if len(texts) == 0:
                document.remove_key("krita_comfyui/output_texts")
            else:
                document.set_key_json("krita_comfyui/output_texts", "krita_comfyui: Output Texts", texts)

        self.display_text(texts)


class ImageWidget(QListWidget):
    image_size = 96
    image_padding = 1
    spacer_height = 4

    number_of_images = 4

    def __init__(self, document):
        super().__init__()

        self.document = document
        self.document.document_changed.connect(self.load_document)

        # Displays the thumbnails at twice the image_size resolution then downscales it
        self.thumbnail_size = self.image_size * 2

        self.storage = ImageStorage(self, self.thumbnail_size)

        self.selected = []
        self.clicked_on_selected = False

        self.image_menus = []
        self.all_menus = []

        self.menu = QMenu(self)
        #self.image_menus.append(self.menu.addSection("Apply images to..."))
        self.image_menus.append(self.menu.addAction(Krita.icon("cloneLayer"), "New layer", self.apply_new_layer))
        self.image_menus.append(self.menu.addAction(Krita.icon("paintLayer"), "Selected layer", self.apply_existing_layer))
        self.image_menus.append(self.menu.addAction(Krita.icon("window-new"), "New document", self.apply_new_document))
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
        self.setMouseTracking(True)
        self.setFixedWidth(self.get_total_width())

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.itemPressed.connect(self.item_pressed, type=Qt.ConnectionType.DirectConnection)
        self.itemActivated.connect(self.item_clicked, type=Qt.ConnectionType.DirectConnection)
        self.itemDoubleClicked.connect(self.item_double_clicked, type=Qt.ConnectionType.DirectConnection)
        # This forces itemSelectionChanged to trigger after itemPressed
        self.itemSelectionChanged.connect(self.selection_changed, type=Qt.ConnectionType.QueuedConnection)

        self.load_document()


    # TODO figure out a more efficient way of doing this
    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)

        item = self.itemAt(event.position().toPoint())

        if item is not None and item.data(Qt.ItemDataRole.UserRole) is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)


    def image_total_size(self):
        return self.image_size + (self.image_padding * 2)


    def get_total_width(self):
        images = self.image_total_size() * self.number_of_images

        scrollbar_width = self.verticalScrollBar().sizeHint().width()

        return scrollbar_width + images + 1


    def load_document(self):
        with BlockSignals(self):
            self.selected = []
            self.clear()

            for group in self.storage.load_all(self.document.current()):
                self.add_images(group, allow_selection=True)


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


    def selected_images(self):
        selected = []

        for item in self.selectedItems():
            data = item.data(Qt.ItemDataRole.UserRole)

            if data is not None:
                selected.append((item, data))

        return selected


    def item_pressed(self, item):
        # This flag determines if we clicked on an item that is already selected. In that case we should deselect it.
        #
        # But we can't deselect it inside of itemPressed, because itemPressed triggers on right click, and we don't want that.
        #
        # So we just set the flag, and let itemActivated do the actual deselection.
        self.clicked_on_selected = item.isSelected() and len(self.selected) == 1 and self.selected[0] is item


    def item_clicked(self, item):
        # We need to use the itemActivated event because the itemPressed event triggers on right click,
        # which we don't want.
        #
        # The itemActivated event is always triggered after itemSelectionChanged, but by then it's too late.
        #
        # The only event that runs before itemSelectionChanged is the itemPressed event.
        #
        # So inside of itemPressed we set a flag, and then read that flag here.
        #
        # That way we avoid running this code on right click, but we're able to read the selection data before
        # the itemSelectionChanged event.
        if self.clicked_on_selected:
            self.clicked_on_selected = False
            self.selected = []
            item.setSelected(False)


    # There is a delay when clicking rapidly, by using itemDoubleClicked we can avoid that delay and
    # select / deselect the item immediately.
    def item_double_clicked(self, item):
        if item.isSelected() and len(self.selected) == 1 and self.selected[0] is item:
            self.selected = []
            item.setSelected(False)

        elif not item.isSelected() and len(self.selected) == 0:
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

        document = self.document.current()

        if document is not None:
            # Show a preview of the last selected image
            if len(selected) > 0:
                image = selected[-1][1]

                name = image["name"]

                document.show_preview_layer(
                    name=f"[Preview] {name}",
                    image=image["image"],
                    x=image["x"],
                    y=image["y"],
                )

            else:
                document.hide_preview_layer()


    def apply_selected_images(self, document):
        with BlockSignals(self):
            self.selected = []

            images = []

            for (item, image) in self.selected_images():
                self.storage.set_applied(document, image["uuid"], True)

                item.setSelected(False)
                item.setIcon(self.thumbnail(image["image"], True))
                images.append(image)

            self.update_selected_state()

            return images


    def get_image_bounds(self, images):
        bounds = None

        for info in images:
            x = info["x"]
            y = info["y"]
            image = info["image"]

            image_bounds = Bounds(x, y, image.width, image.height)

            if bounds is None:
                bounds = image_bounds
            else:
                bounds = bounds.union(image_bounds)

        return bounds


    def apply_new_layer(self):
        document = self.document.current()

        if document is not None:
            selected_images = self.apply_selected_images(document)

            bounds = self.get_image_bounds(selected_images)

            document.remove_preview_layer()

            for info in selected_images:
                layer = Layer.fromImage(document, info["name"], info["image"], info["x"], info["y"])
                layer.move_to_top(document.root_layer())

                #activeLayer = document.active_layer()
                #parent = activeLayer.parent
                #parent.insert_child(layer, activeLayer)

            if bounds is not None:
                new_position = document.scale_to_bounds(bounds)

                if new_position is not None:
                    pass


    def apply_existing_layer(self):
        document = self.document.current()

        if document is not None:
            activeLayer = document.active_layer()

            selected_images = self.apply_selected_images(document)

            bounds = self.get_image_bounds(selected_images)

            document.remove_preview_layer()

            for info in selected_images:
                activeLayer.write_image(info["image"], info["x"], info["y"])

            if bounds is not None:
                new_position = document.scale_to_bounds(bounds)

                if new_position is not None:
                    pass

                else:
                    document.refresh()
            else:
                document.refresh()


    def apply_new_document(self):
        document = self.document.current()

        if document is not None:
            profile = document.color_profile()
            resolution = document.pixels_per_inch()

            # If we remove the preview layer then it causes the global selection mask to break.
            document.hide_preview_layer()

            selected_images = self.apply_selected_images(document)

            bounds = self.get_image_bounds(selected_images)

            new_document = Document.create(
                bounds.width,
                bounds.height,
                document.name,
                # TODO copy these from the existing document?
                "RGBA",
                "U8",
                profile,
                resolution,
            )

            for layer in new_document.root_layer().all_children():
                layer.remove()

            for info in selected_images:
                layer = Layer.fromImage(new_document, info["name"], info["image"], info["x"] - bounds.x, info["y"] - bounds.y)
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

            document = self.document.current()
            if document is not None:
                if self.count() == 0:
                    document.remove_preview_layer()
                else:
                    document.hide_preview_layer()

                self.storage.remove(document, uuids)


    # Returns true if the previous image is single
    def is_previous_single(self):
        for i in reversed(range(self.count())):
            item = self.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)

            # We found a spacer, so stop searching
            if data is None:
                return True
            else:
                return data["is_single"]

        return True


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
                    document.remove_preview_layer()
                    self.storage.clear(document)

                self.selected = []
                self.clear()


    def add_spacer(self, height):
        spacer = QListWidgetItem("")
        spacer.setFlags(Qt.ItemFlag.NoItemFlags)
        spacer.setData(Qt.ItemDataRole.UserRole, None)
        spacer.setSizeHint(QSize(9999, height))
        spacer.setTextAlignment(Qt.AlignmentFlag.AlignLeft)
        self.addItem(spacer)


    def add_image(self, info, *, size, is_single, allow_selection):
        tooltip = info["name"]

        item = QListWidgetItem(self.thumbnail(info["image"], applied=info["applied"]), None)

        item.setSizeHint(QSize(size, size))

        item.setData(Qt.ItemDataRole.UserRole, {
            "uuid": info["uuid"],
            "image": info["image"],
            "x": info["x"],
            "y": info["y"],
            "name": info["name"],
            "is_single": is_single,
        })

        item.setData(Qt.ItemDataRole.ToolTipRole, tooltip)

        self.addItem(item)

        if info["selected"]:
            assert allow_selection
            item.setSelected(True)
            self.selected.append(item)


    def add_images(self, group, *, allow_selection):
        with BlockSignals(self):
            # The group contains a single image.
            is_single = len(group) == 1 and len(group[0]) == 1

            # If both the current and previous group contained a single
            # image, we merge them together into one batch.
            should_merge = is_single and self.is_previous_single()

            # In between groups we add a regular spacer.
            spacer_height = self.spacer_height

            size = self.image_total_size()

            for batch in group:
                if not should_merge:
                    if self.count() > 0:
                        self.add_spacer(spacer_height)

                        # In between each batch we add a small spacer.
                        spacer_height = 0

                for info in batch:
                    self.add_image(info, size=size, is_single=is_single, allow_selection=allow_selection)

            #self.scrollToBottom()


    def new_images(self, group):
        if len(group) > 0:
            document = self.document.current()

            if document is not None:
                self.add_images(self.storage.save_group(document, group), allow_selection=False)


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

        self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred))

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

            # The image group is sorted by the order.
            self.add_images([batch for order, batch in sorted(images.items(), key=lambda x: x[0])])

            # Sort text by order and name
            texts.sort(key=lambda x: (x["order"], x["name"].casefold()))

            self.set_text(texts)


    def set_text(self, texts):
        self._widget.text.set_text(texts)

    def add_images(self, group):
        self._widget.image.new_images(group)

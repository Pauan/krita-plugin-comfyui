from PyQt6.QtCore import QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QSizePolicy,
)
from ...util.krita import Image, Bounds
from ...util.qt import MessageBox, BlockSignals
from .serialized import SerializedImages


class ImageWidget(QListWidget):
    image_size = 96
    image_padding = 1
    spacer_height = 4

    number_of_images = 4

    total_bytes_changed = pyqtSignal()

    def __init__(self, document):
        super().__init__()

        self.document = document
        self.document.document_changed.connect(self.load_document)

        self.total_bytes = 0

        # Displays the thumbnails at twice the image_size resolution then downscales it
        self.thumbnail_size = self.image_size * 2

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
        self.setFrameStyle(QFrame.Shape.Panel)
        self.setFrameShadow(QFrame.Shadow.Sunken)
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

        return scrollbar_width + images + 3


    def load_document(self):
        old_bytes = self.total_bytes

        with BlockSignals(self):
            self.total_bytes = 0
            self.selected = []
            self.clear()

            document = self.document.current()

            if document is None:
                self.images = None

            else:
                self.images = SerializedImages.load(document)

                for group in self.images.get_images():
                    self.add_images(group, allow_selection=True)

        if self.total_bytes != old_bytes:
            self.total_bytes_changed.emit()


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


    def all_data(self):
        for i in range(self.count()):
            item = self.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)

            if data is not None:
                yield item, data


    # When images are selected / deselected we have to serialize that information.
    def update_selected_state(self, document):
        for item, data in self.all_data():
            self.images.get_image(data["uuid"]).set_selected(document, item.isSelected())


    # When the canvas is resized / scaled we have to shift the {x, y} of all the
    # images so that they are properly aligned with the new canvas bounds.
    def update_position(self, document, x, y):
        if x != 0 or y != 0:
            for item, data in self.all_data():
                self.images.get_image(data["uuid"]).update_position(document, x, y)


    def maybe_show_preview(self, document, selected):
        # Show a preview of the last selected image
        if len(selected) > 0:
            data = selected[-1][1]
            self.images.get_image(data["uuid"]).show_preview(document)

        else:
            document.hide_preview_layer()


    def update_preview(self):
        document = self.document.current()

        if document is not None:
            self.maybe_show_preview(document, self.selected_images())


    def selection_changed(self):
        selected = self.selected_images()

        self.selected = [item for (item, _) in selected]

        document = self.document.current()

        if document is not None:
            self.update_selected_state(document)
            self.maybe_show_preview(document, selected)


    def deselect_all_images(self):
        with BlockSignals(self):
            for item in self.selectedItems():
                item.setSelected(False)

            self.selected = []

            document = self.document.current()

            if document is not None:
                self.update_selected_state(document)
                document.hide_preview_layer()


    def apply_selected_images(self, document):
        with BlockSignals(self):
            self.selected = []

            images = []

            for (item, data) in self.selected_images():
                image = self.images.get_image(data["uuid"])

                # It doesn't need to save the metadata because the metadata will be saved by update_selected_state
                image.set_applied(document, True, save=False)

                # This ensures that the metadata will be properly saved by update_selected_state
                assert image.is_selected()
                assert item.isSelected()
                item.setSelected(False)
                assert not item.isSelected()

                item.setIcon(self.thumbnail(image.image, True))
                images.append(image)

            self.update_selected_state(document)
            return images


    def apply_new_layer(self):
        document = self.document.current()

        if document is not None:
            selected_images = self.apply_selected_images(document)
            bounds = SerializedImages.apply_new_layers(document, selected_images)
            self.update_position(document, bounds.x, bounds.y)


    def apply_existing_layer(self):
        document = self.document.current()

        if document is not None:
            selected_images = self.apply_selected_images(document)
            bounds = SerializedImages.apply_existing_layer(document, selected_images)
            self.update_position(document, bounds.x, bounds.y)


    def apply_new_document(self):
        document = self.document.current()

        if document is not None:
            selected_images = self.apply_selected_images(document)
            SerializedImages.apply_new_document(document, selected_images)


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

                old_bytes = self.total_bytes

                for serialized in self.images.remove_uuids(document, uuids):
                    self.total_bytes -= serialized.image.byte_size()
                    assert self.total_bytes >= 0

                if self.total_bytes != old_bytes:
                    self.total_bytes_changed.emit()


    def delete_all(self):
        if MessageBox.question(self, "Are you sure you want to delete all ComfyUI output images?"):
            old_bytes = self.total_bytes

            with BlockSignals(self):
                document = self.document.current()

                if document is not None:
                    document.remove_preview_layer()
                    self.images.clear(document)

                self.total_bytes = 0
                self.selected = []
                self.clear()

            if self.total_bytes != old_bytes:
                self.total_bytes_changed.emit()


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


    def add_spacer(self, height):
        spacer = QListWidgetItem("")
        spacer.setFlags(Qt.ItemFlag.NoItemFlags)
        spacer.setData(Qt.ItemDataRole.UserRole, None)
        spacer.setSizeHint(QSize(9999, height))
        spacer.setTextAlignment(Qt.AlignmentFlag.AlignLeft)
        self.addItem(spacer)


    def add_image(self, serialized, *, size, is_single, allow_selection):
        item = QListWidgetItem(self.thumbnail(serialized.image, applied=serialized.is_applied()), None)

        item.setSizeHint(QSize(size, size))

        item.setData(Qt.ItemDataRole.UserRole, {
            "uuid": serialized.uuid,
            "is_single": is_single,
        })

        item.setData(Qt.ItemDataRole.ToolTipRole, serialized.tooltip())

        self.addItem(item)

        self.total_bytes += serialized.image.byte_size()

        if serialized.is_selected():
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

                for serialized in batch:
                    self.add_image(serialized, size=size, is_single=is_single, allow_selection=allow_selection)

            #self.scrollToBottom()


    def new_images(self, document, group):
        if self.document.is_equal(document):
            old_bytes = self.total_bytes

            self.add_images(self.images.add_new_group(document, group), allow_selection=False)

            if self.total_bytes != old_bytes:
                self.total_bytes_changed.emit()

        else:
            # Since it's in a different document, we save the images
            # inside of a new SerializedImages for that document.
            #
            # Since it's in another document we don't need to load
            # the existing images, we only need to save new images.
            SerializedImages.load(document, load_images=False).add_new_group(document, group)


    def job_started(self):
        self.deselect_all_images()


    def show_context_menu(self, pos: QPoint):
        images_selected = len(self.selected_images()) > 0

        has_images = self.count() > 0

        for menu in self.image_menus:
            menu.setEnabled(images_selected)

        for menu in self.all_menus:
            menu.setEnabled(has_images)

        self.menu.exec(self.mapToGlobal(pos))

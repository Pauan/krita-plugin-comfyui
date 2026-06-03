from PyQt6.QtCore import QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QPalette, QIcon
from PyQt6.QtWidgets import (
    QLabel,
    QFrame,
    QMenu,
    QSizePolicy,
)
from ...util.qt import MessageBox, LayoutManager
from ...util.krita import Image
from .serialized import SerializedImages, SerializedImage


class LiveModeImage(QLabel):
    def __init__(self, root, extension, document, warning_widget):
        super().__init__()

        self.root = root

        self.extension = extension
        self.document = document
        self.document.document_changed.connect(self.load_image)

        self.warning_widget = warning_widget

        self.layout_manager = LayoutManager(self)

        self.image_width = 0
        self.image_height = 0

        self.current_image = None

        self.image_menus = []

        self.menu = QMenu(self)
        self.image_menus.append(self.menu.addAction(Krita.icon("cloneLayer"), "New layer", self.apply_new_layer))
        self.image_menus.append(self.menu.addAction(Krita.icon("paintLayer"), "Selected layer", self.apply_existing_layer))
        self.image_menus.append(self.menu.addAction(Krita.icon("window-new"), "New document", self.apply_new_document))
        self.menu.addSeparator()
        self.image_menus.append(self.menu.addAction(Krita.icon("deletelayer"), "Delete", self.delete_all))

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.setScaledContents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.apply_image = QLabel(self)
        self.apply_image.setPixmap(QIcon(Image.filename("diamond.svg")).pixmap(QSize(19, 19)))
        self.apply_image.setFixedSize(QSize(19, 19))
        self.apply_image.setContentsMargins(0, 0, 0, 0)
        self.apply_image.setVisible(False)

        with self.layout_manager.column() as column:
            with column.label() as label:
                self.overlay = label

                self.overlay.setVisible(False)

                highlight = self.palette().color(QPalette.ColorRole.Highlight)
                r = highlight.red()
                g = highlight.green()
                b = highlight.blue()

                # TODO figure out a way to automatically use the correct alpha
                self.overlay.setStyleSheet(f"""
                    QLabel {{
                        background-color: rgba({r}, {g}, {b}, 30%);
                        border: 1px solid rgb({r}, {g}, {b});
                    }}
                """)

        self.load_image()


    def update_margins(self):
        if self.image_width > 0 and self.image_height > 0:
            width = self.width()
            height = self.height()

            if width > 0 and height > 0:
                desired_ratio = self.image_width / self.image_height
                actual_ratio = width / height

                # Image is too tall, shrink it vertically
                if actual_ratio < desired_ratio:
                    margin = max(0, int((height - (width / desired_ratio)) * 0.5))
                    self.setContentsMargins(0, margin, 0, margin)
                    self.apply_image.move(4, 4 + margin)
                    return

                # Image is too wide, shrink it horizontally
                elif actual_ratio > desired_ratio:
                    margin = max(0, int((width - (height * desired_ratio)) * 0.5))
                    self.setContentsMargins(margin, 0, margin, 0)
                    self.apply_image.move(4 + margin, 4)
                    return

        self.setContentsMargins(0, 0, 0, 0)


    def load_image(self):
        document = self.document.current()

        if document is not None:
            self.warning_widget.load(document)

            serialized = SerializedImage.load(document, SerializedImage.live_mode_uuid())

            if serialized is not None:
                self.set_image(serialized)
            else:
                self.clear_image()

        else:
            self.warning_widget.hide()
            self.clear_image()


    def update_total_bytes(self, value):
        if self.root.total_bytes != value:
            self.root.total_bytes = value
            self.root.total_bytes_changed.emit()


    def clear_image(self):
        self.current_image = None

        self.setToolTip("")

        self.update_total_bytes(0)

        self.image_width = 0
        self.image_height = 0
        self.update_margins()

        self.clear()
        self.overlay.setVisible(False)
        self.apply_image.setVisible(False)


    def update_applied(self):
        self.apply_image.setVisible(self.current_image.is_applied())


    def set_image(self, serialized):
        self.current_image = serialized

        self.setToolTip(serialized.tooltip())

        self.update_total_bytes(serialized.image.byte_size())

        self.image_width = serialized.image.width
        self.image_height = serialized.image.height
        self.update_margins()

        self.setPixmap(serialized.image.to_pixmap())
        self.overlay.setVisible(serialized.is_selected())
        self.update_applied()


    @staticmethod
    def flattened_images(group):
        return [info for batch in group for info in batch]


    def new_image(self, document, group, is_visible):
        with self.extension.disable_live_mode(), document.disable_modification():
            images = self.flattened_images(group)


            if len(images) > 1:
                warning = f"Generated {len(images)} images, only showing the last one."
            else:
                warning = None

            self.warning_widget.store(document, warning)


            is_same_document = self.document.is_equal(document)

            if is_same_document:
                if warning is None:
                    self.warning_widget.hide()
                else:
                    self.warning_widget.show(warning)

                current_image = self.current_image
            else:
                current_image = SerializedImage.load(document, SerializedImage.live_mode_uuid())


            if current_image is None:
                selected = False
            else:
                selected = current_image.is_selected()


            # If there are multiple images we use the last one.
            serialized = SerializedImage.save_new_image(document, SerializedImage.live_mode_uuid(), images[-1])
            assert not serialized.is_selected()

            if selected:
                serialized.set_selected(document, selected)

            if is_same_document:
                self.set_image(serialized)

                if is_visible:
                    self.update_image_preview(document)


    def set_selected(self, document, selected, *, update_preview=True):
        self.current_image.set_selected(document, selected)

        self.overlay.setVisible(selected)

        if update_preview:
            self.update_image_preview(document)


    def update_image_preview(self, document):
        if self.current_image is not None and self.current_image.is_selected():
            self.current_image.show_preview(document)
        else:
            document.hide_preview_layer()


    def update_preview(self):
        document = self.document.current()

        if document is not None:
            with self.extension.disable_live_mode(), document.disable_modification():
                self.update_image_preview(document)


    def on_image_clicked(self):
        document = self.document.current()

        if document is not None:
            if self.current_image is not None:
                with self.extension.disable_live_mode(), document.disable_modification():
                    self.set_selected(document, not self.current_image.is_selected())


    def job_started(self):
        document = self.document.current()

        if document is not None:
            if self.current_image is not None:
                with self.extension.disable_live_mode(), document.disable_modification():
                    self.set_selected(document, False)


    def apply_selected(self, document):
        self.set_selected(document, False, update_preview=False)
        self.current_image.set_applied(document, True)
        self.update_applied()


    def apply_new_layer(self):
        document = self.document.current()

        if document is not None:
            if self.current_image is not None:
                with self.extension.disable_live_mode():
                    self.apply_selected(document)

                    # TODO update the bounds of non-live images
                    SerializedImages.apply_new_layers(document, [self.current_image])


    def apply_existing_layer(self):
        document = self.document.current()

        if document is not None:
            if self.current_image is not None:
                with self.extension.disable_live_mode():
                    self.apply_selected(document)

                    # TODO update the bounds of non-live images
                    SerializedImages.apply_existing_layer(document, [self.current_image])


    def apply_new_document(self):
        document = self.document.current()

        if document is not None:
            if self.current_image is not None:
                with self.extension.disable_live_mode():
                    self.apply_selected(document)

                    SerializedImages.apply_new_document(document, [self.current_image])


    def delete_all(self):
        if MessageBox.question(self, "Are you sure you want to delete the live mode image?"):
            with self.extension.disable_live_mode():
                document = self.document.current()

                if document is not None:
                    with document.disable_modification():
                        if self.current_image is not None:
                            self.current_image.remove(document)

                        document.remove_preview_layer()
                        self.warning_widget.store(document, None)

                self.warning_widget.hide()
                self.clear_image()


    def show_context_menu(self, pos: QPoint):
        has_image = self.current_image is not None

        document = self.document.current()

        if document is not None:
            if has_image:
                with self.extension.disable_live_mode(), document.disable_modification():
                    self.set_selected(document, True)

        for menu in self.image_menus:
            menu.setEnabled(has_image)

        self.menu.exec(self.mapToGlobal(pos))


    def resizeEvent(self, event):
        self.update_margins()
        super().resizeEvent(event)


    def mousePressEvent(self, event):
        super().mousePressEvent(event)

        if event.buttons() == Qt.MouseButton.LeftButton:
            self.on_image_clicked()


class LiveModeWarning(QFrame):
    def __init__(self):
        super().__init__()

        self.layout_manager = LayoutManager(self)

        self.setVisible(False)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setFrameShape(QFrame.Shape.Panel)
        self.setFrameShadow(QFrame.Shadow.Raised)

        self.setStyleSheet("""
            QFrame {
                padding: 6px;
                color: white;
                background-color: #6b1400;
            }
        """)

        with self.layout_manager.row() as row:
            with row.icon(Krita.icon("warning"), width=16, height=16) as icon:
                icon.setContentsMargins(0, 0, 0, 0)

            with row.label(stretch=1) as label:
                self.warning_label = label
                label.setContentsMargins(0, 0, 0, 0)


    def store(self, document, value):
        if value is None:
            document.remove_key("krita_comfyui/live_mode_warning")
        else:
            document.set_key_str("krita_comfyui/live_mode_warning", "krita_comfyui: Live Mode Warning", value)


    def load(self, document):
        message = document.get_key_str("krita_comfyui/live_mode_warning", None)

        if message is None:
            self.hide()
        else:
            self.show(message)


    def hide(self):
        self.setVisible(False)


    def show(self, message):
        self.warning_label.setText(message)
        self.setVisible(True)


class LiveModeWidget(QFrame):
    total_bytes_changed = pyqtSignal()


    def __init__(self, extension, document):
        super().__init__()

        self.total_bytes = 0

        self.layout_manager = LayoutManager(self)

        self.setAutoFillBackground(True)
        self.setBackgroundRole(QPalette.ColorRole.Base)
        self.setFrameStyle(QFrame.Shape.Panel)
        self.setFrameShadow(QFrame.Shadow.Sunken)

        # This causes it to shrink the image to fit within the space.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        with self.layout_manager.column() as column:
            with column.widget(LiveModeWarning()) as warning:
                self.warning_widget = warning

            with column.widget(LiveModeImage(self, extension, document, self.warning_widget)) as widget:
                self.image_widget = widget


    def new_images(self, document, group, is_visible):
        self.image_widget.new_image(document, group, is_visible)


    def job_started(self):
        self.image_widget.job_started()


    def update_preview(self):
        self.image_widget.update_preview()

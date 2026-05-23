from PyQt6.QtCore import QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import (
    QLabel,
    QFrame,
    QMenu,
    QMessageBox,
    QSizePolicy,
)
from ...util.qt import LayoutManager
from .serialized import SerializedImages, SerializedImage


class LiveModeImage(QLabel):
    clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.image_width = 0
        self.image_height = 0
        self.setScaledContents(True)


    def set_image(self, image):
        if image is None:
            self.image_width = 0
            self.image_height = 0
            self.update_margins()
            self.clear()
        else:
            self.image_width = image.width
            self.image_height = image.height
            self.update_margins()
            self.setPixmap(image.to_pixmap())


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
                    return

                # Image is too wide, shrink it horizontally
                elif actual_ratio > desired_ratio:
                    margin = max(0, int((width - (height * desired_ratio)) * 0.5))
                    self.setContentsMargins(margin, 0, margin, 0)
                    return

        self.setContentsMargins(0, 0, 0, 0)


    def resizeEvent(self, event):
        self.update_margins()
        super().resizeEvent(event)


    def mousePressEvent(self, event):
        super().mousePressEvent(event)

        if event.buttons() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


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
            with row.label() as icon:
                icon.setContentsMargins(0, 0, 0, 0)
                icon.setPixmap(Krita.icon("warning").pixmap(QSize(16, 16)))

            with row.label(stretch=1) as label:
                self.warning_label = label
                label.setContentsMargins(0, 0, 0, 0)


    def hide(self):
        self.setVisible(False)


    def show(self, message):
        self.warning_label.setText(message)
        self.setVisible(True)


class LiveModeWidget(QFrame):
    def __init__(self, document):
        super().__init__()

        self.document = document
        self.document.document_changed.connect(self.load_image)

        self.layout_manager = LayoutManager(self)

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

        self.setAutoFillBackground(True)
        self.setBackgroundRole(QPalette.ColorRole.Base)
        self.setFrameStyle(QFrame.Shape.Panel)
        self.setFrameShadow(QFrame.Shadow.Sunken)

        # This causes it to shrink the image to fit within the space.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        with self.layout_manager.column() as column:
            with column.widget(LiveModeWarning()) as warning:
                self.warning_widget = warning

            with column.widget(LiveModeImage()) as widget:
                self.image_widget = widget
                widget.clicked.connect(self.on_image_clicked)

        self.load_image()


    def load_image(self):
        document = self.document.current()

        if document is not None:
            serialized = SerializedImage.load(document, SerializedImage.live_mode_uuid())

            if serialized is not None:
                self.set_image(document, serialized)
                return

        self.clear_image()


    def clear_image(self):
        self.current_image = None
        self.image_widget.set_image(None)


    def set_image(self, document, serialized):
        self.current_image = serialized
        self.image_widget.set_image(serialized.image)


    @staticmethod
    def flattened_images(group):
        return [info for batch in group for info in batch]


    def new_images(self, document, group):
        images = self.flattened_images(group)

        if len(images) > 1:
            self.warning_widget.show(f"Generated {len(images)} images, only showing the last one.")
        else:
            self.warning_widget.hide()

        # If there are multiple images we use the last one.
        serialized = SerializedImage.save_new_image(document, SerializedImage.live_mode_uuid(), images[-1])

        self.set_image(document, serialized)

        document.hide_preview_layer()


    def show_context_menu(self, pos: QPoint):
        document = self.document.current()

        if document is not None:
            if self.current_image is not None:
                self.current_image.set_selected(document, True)
                self.update_image_preview(document)

        has_image = self.current_image is not None

        for menu in self.image_menus:
            menu.setEnabled(has_image)

        self.menu.exec(self.mapToGlobal(pos))


    def update_image_preview(self, document):
        if self.current_image.is_selected():
            self.current_image.show_preview(document)
        else:
            document.hide_preview_layer()


    def update_preview(self):
        document = self.document.current()

        if document is not None:
            self.update_image_preview(document)


    def on_image_clicked(self):
        document = self.document.current()

        if document is not None:
            if self.current_image is not None:
                is_selected = self.current_image.is_selected()
                self.current_image.set_selected(document, not is_selected)
                self.update_image_preview(document)


    def apply_new_layer(self):
        document = self.document.current()

        if document is not None:
            if self.current_image is not None:
                # TODO update the bounds of non-live images
                SerializedImages.apply_new_layers(document, [self.current_image])


    def apply_existing_layer(self):
        document = self.document.current()

        if document is not None:
            if self.current_image is not None:
                # TODO update the bounds of non-live images
                SerializedImages.apply_existing_layer(document, [self.current_image])


    def apply_new_document(self):
        document = self.document.current()

        if document is not None:
            if self.current_image is not None:
                SerializedImages.apply_new_document(document, [self.current_image])


    def delete_all(self):
        reply = QMessageBox.question(
            self,
            "Delete live mode",
            "Are you sure you want to delete the live mode image?",
        )

        if reply == QMessageBox.StandardButton.Yes:
            document = self.document.current()

            if document is not None:
                if self.current_image is not None:
                    self.current_image.remove(document)

                document.remove_preview_layer()

            self.clear_image()

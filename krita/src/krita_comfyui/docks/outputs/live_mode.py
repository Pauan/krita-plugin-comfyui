from PyQt6.QtCore import QPoint, QSize, Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import (
    QLabel,
    QFrame,
    QMenu,
    QMessageBox,
    QSizePolicy,
)
from ...util.qt import LayoutManager
from .serializer import ImageSerializer


class LiveModeImage(QLabel):
    def __init__(self):
        super().__init__()
        self.image_width = 0
        self.image_height = 0
        self.setScaledContents(True)


    def set_image(self, image):
        self.image_width = image.width
        self.image_height = image.height
        self.update_margins()
        self.setPixmap(image.to_pixmap())


    def update_margins(self):
        if self.image_width > 0 and self.image_height > 0:
            width = self.width()
            height = self.height()

            if width > 0 and height > 0:
                if width * self.image_height > height * self.image_width:
                    margin = int((width - (self.image_width * height / self.image_height)) / 2)
                    self.setContentsMargins(margin, 0, margin, 0)
                    return
                else:
                    margin = int((height - (self.image_height * width / self.image_width)) / 2)
                    self.setContentsMargins(0, margin, 0, margin)
                    return

        self.setContentsMargins(0, 0, 0, 0)


    def resizeEvent(self, event):
        self.update_margins()
        super().resizeEvent(event)


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

        #self.document = document
        #self.document.document_changed.connect(self.load_document)

        self.image_serializer = ImageSerializer()
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


    def set_image(self, image, metadata):
        self.current_image = {
            "image": image,
            "metadata": metadata,
        }

        self.image_widget.set_image(image)


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
        info = images[-1]
        image, metadata = self.image_serializer.process_new_image(info)
        self.set_image(image, metadata)


    def show_context_menu(self, pos: QPoint):
        has_image = self.current_image is not None

        for menu in self.image_menus:
            menu.setEnabled(has_image)

        self.menu.exec(self.mapToGlobal(pos))


    def apply_new_layer(self):
        pass


    def apply_existing_layer(self):
        pass


    def apply_new_document(self):
        pass


    def delete_all(self):
        pass

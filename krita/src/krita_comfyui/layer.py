from pathlib import Path
from enum import Enum
from PyQt6 import sip
from typing import NamedTuple
from json import (dumps, loads)
import numpy as np

from PyQt6.QtCore import QObject, QByteArray, QRect, QBuffer, QUuid, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPainter, QPixmap, QImage, QImageWriter


class CurrentDocument(QObject):
    changed = pyqtSignal()


    def __init__(self, parent):
        super().__init__(parent)

        self._document = None


    def is_equal(self, new):
        if self._document is None and new is None:
            return True
        elif self._document is not None and new is not None:
            return self._document._document == new._document
        else:
            return False


    def current(self):
        document = Document.current()

        if self.is_equal(document):
            return self._document


    def check_current(self):
        document = Document.current()

        if not self.is_equal(document):
            self._document = document
            self.changed.emit()


class BlockSignals:
    def __init__(self, obj: QObject):
        self.obj = obj

    def __enter__(self):
        self.obj.blockSignals(True)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.obj.blockSignals(False)
        return False


class Bounds(NamedTuple):
    x: int
    y: int
    width: int
    height: int

    @staticmethod
    def from_qrect(qrect: QRect):
        return Bounds(qrect.x(), qrect.y(), qrect.width(), qrect.height())


    def to_qrect(self):
        return QRect(self.x, self.y, self.width, self.height)


    def clamp_to_parent(self, parent):
        x = max(parent.x, self.x)
        y = max(parent.y, self.y)
        width = max(0, min(parent.x + parent.width, self.x + self.width) - x)
        height = max(0, min(parent.y + parent.height, self.y + self.height) - y)

        assert x >= parent.x
        assert y >= parent.y
        assert width >= 0
        assert height >= 0
        assert (x + width) <= (parent.x + parent.width)
        assert (y + height) <= (parent.y + parent.height)

        return Bounds(x, y, width, height)


    def area(self):
        return self.width * self.height


class HideModifications:
    def __init__(self, document):
        self.document = document

    def __enter__(self):
        self.modified = self.document.modified()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.document.setModified(self.modified)
        return False


class ActiveNode:
    def __init__(self, document):
        self.document = document

    def __enter__(self):
        self.active = self.document.activeNode()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.document.setActiveNode(self.active)
        return False


class Selection:
    def __init__(self, selection):
        self._selection = selection

    def copy(self):
        return Selection(self._selection.duplicate())

    def feather(self, radius):
        self._selection.feather(radius)

    def grow(self, horizontal, vertical):
        self._selection.grow(horizontal, vertical)

    def mask(self, bounds):
        bytes = self._selection.pixelData(bounds.x, bounds.y, bounds.width, bounds.height)
        return Mask.from_packed_bytes(bytes, bounds.width, bounds.height)

    def bounds(self):
        return Bounds(self._selection.x(), self._selection.y(), self._selection.width(), self._selection.height())


class Document:
    def __init__(self, document):
        self._document = document


    @staticmethod
    def current():
        document = Krita.instance().activeDocument()
        if document is not None:
            return Document(document)


    @staticmethod
    def create(width, height, name, color_model, color_depth, color_profile, pixels_per_inch):
        new_document = Document(Krita.instance().createDocument(
            width,
            height,
            name,
            color_model,
            color_depth,
            color_profile,
            pixels_per_inch,
        ))

        Krita.instance().activeWindow().addView(new_document._document)

        return new_document


    def remove_key(self, key):
        self._document.removeAnnotation(key)


    def get_key_bytes(self, key):
        value = self._document.annotation(key)
        if value.size() > 0:
            return value

    def set_key_bytes(self, key, description, value: bytes):
        self._document.setAnnotation(key, description, QByteArray(value))


    def get_key_str(self, key):
        value = self.get_key_bytes(key)
        if value is not None:
            return value.data().decode("utf-8")

    def set_key_str(self, key, description, value: str):
        self.set_key_bytes(key, description, value.encode("utf-8"))


    def get_key_json(self, key):
        value = self.get_key_str(key)
        if value is not None:
            return loads(value)

    def set_key_json(self, key, description, json):
        self.set_key_str(key, description, dumps(json))


    def bounds(self):
        return Bounds.from_qrect(self._document.bounds())


    def selection(self):
        selection = self._document.selection()

        if selection is not None:
            return Selection(selection)


    def refresh(self):
        self._document.refreshProjection()


    def canvas(self, bounds):
        with HideModifications(self._document):
            preview = self.find_preview_layer()

            if preview is not None:
                visible = preview.is_visible

                try:
                    if visible:
                        preview.is_visible = False

                    self.refresh()
                    #return Image.from_packed_bytes(self._document.pixelData(bounds.x, bounds.y, bounds.width, bounds.height), bounds.width, bounds.height)
                    return Image(self._document.projection(bounds.x, bounds.y, bounds.width, bounds.height))

                finally:
                    if visible:
                        preview.is_visible = visible
                        self.refresh()

            else:
                self.refresh()
                #return Image.from_packed_bytes(self._document.pixelData(bounds.x, bounds.y, bounds.width, bounds.height), bounds.width, bounds.height)
                return Image(self._document.projection(bounds.x, bounds.y, bounds.width, bounds.height))


    def root_layer(self):
        node = self._document.rootNode()
        if node is not None:
            return Layer(node)

    def active_layer(self):
        node = self._document.activeNode()
        if node is not None:
            return Layer(node)

    def pixels_per_inch(self):
        return self._document.resolution()

    def color_profile(self):
        return self._document.colorProfile()


    def new_paint_layer(self, name):
        return Layer(self._document.createNode(name, "paintLayer"))


    def find_layer_by_name(self, name):
        layer = self._document.nodeByName(name)
        if layer is not None:
            return Layer(layer)

    def find_layer_by_id(self, id: str):
        layer = self._document.nodeByUniqueID(QUuid(id))
        if layer is not None:
            return Layer(layer)


    def find_preview_layer(self):
        id = self.get_key_str("krita_comfyui/preview_layer")

        if id is not None:
            layer = self.find_layer_by_id(id)

            if layer is None:
                self.remove_key("krita_comfyui/preview_layer")
            else:
                return layer


    def remove_preview_layer(self):
        with HideModifications(self._document):
            layer = self.find_preview_layer()

            if layer is not None:
                layer.remove()

            self.remove_key("krita_comfyui/preview_layer")


    def hide_preview_layer(self):
        with HideModifications(self._document):
            layer = self.find_preview_layer()

            if layer is not None:
                layer.is_visible = False
                self.refresh()


    def show_preview_layer(self, name, image, x, y):
        with HideModifications(self._document), ActiveNode(self._document):
            layer = self.find_preview_layer()

            if layer is None:
                layer = self.new_paint_layer(name)

                self.set_key_str("krita_comfyui/preview_layer", "krita_comfyui: Preview Layer ID", layer.id)

            layer.replace_image(image, x, y)

            layer.name = name
            layer.is_visible = True
            layer.is_locked = True
            layer.move_to_top(self.root_layer())


class Mask:
    def __init__(self, qimage: QImage):
        self._qimage = qimage


    @staticmethod
    def solid(value, width, height):
        qimage = QImage(width, height, QImage.Format.Format_Grayscale8)
        qimage.fill(value)
        return Mask(qimage)


    @staticmethod
    def from_packed_bytes(data: QByteArray, width, height):
        stride = width
        qimg = QImage(data, width, height, stride, QImage.Format.Format_Grayscale8)
        return Mask(qimg)


    @property
    def width(self):
        return self._qimage.width()

    @property
    def height(self):
        return self._qimage.height()


    def is_solid(self, value):
        bytes = self._qimage.constBits()

        array = np.frombuffer(bytes, dtype=np.uint8).reshape(self.height, self.width, 1)

        print(array)

        return np.all(array[:, :, 0] == value)


    def to_base64(self, format, quality):
        return Image(self._qimage).to_base64(format, quality)


class Image:
    def __init__(self, qimage: QImage):
        self._qimage = qimage


    @staticmethod
    def filename(name: str):
        return str(Path(__file__).parent / "images" / name)


    @staticmethod
    def load_file(filename: str):
        path = Image.filename(filename)
        image = QImage()
        if not image.load(path):
            raise RuntimeError("Failed to load image {}", path)
        return Image(image)


    @staticmethod
    def from_base64(data: str, format: str):
        bytes = QByteArray.fromBase64(data.encode("utf-8"))
        image = QImage.fromData(bytes, format)
        return Image(image)


    @staticmethod
    def from_packed_bytes(data: QByteArray, width, height):
        stride = width * 4
        qimg = QImage(data, width, height, stride, QImage.Format.Format_ARGB32)
        return Image(qimg)


    @property
    def width(self):
        return self._qimage.width()

    @property
    def height(self):
        return self._qimage.height()

    def bytes(self):
        ptr = self._qimage.constBits()
        return QByteArray(ptr.asstring(self._qimage.sizeInBytes()))


    def scale_to_fit(self, width, height):
        scale = min(width / self.width, height / self.height)

        # Scale the width / height while keeping the same aspect ratio
        width = int(round(self.width * scale))
        height = int(round(self.height * scale))

        if self.width == width and self.height == height:
            return self

        mode = Qt.AspectRatioMode.IgnoreAspectRatio
        quality = Qt.TransformationMode.SmoothTransformation
        scaled = self._qimage.scaled(width, height, mode, quality)
        return Image(scaled)


    def draw_image(self, image, bounds: Bounds):
        mode = QPainter.CompositionMode.CompositionMode_SourceOver
        painter = QPainter(self._qimage)
        painter.setCompositionMode(mode)
        painter.drawImage(bounds.to_qrect(), image._qimage)
        painter.end()


    def draw_icon(self, icon: QIcon, bounds: Bounds, alignment: Qt.AlignmentFlag, state: QIcon.State):
        mode = QPainter.CompositionMode.CompositionMode_SourceOver
        painter = QPainter(self._qimage)
        painter.setCompositionMode(mode)
        icon.paint(painter, bounds.to_qrect(), alignment, QIcon.Mode.Normal, state)
        painter.end()


    def to_icon(self):
        pixmap = QPixmap.fromImage(self._qimage)
        return QIcon(pixmap)


    def write(self, buffer, format, quality):
        writer = QImageWriter(buffer, QByteArray(format.encode("utf-8")))
        writer.setQuality(quality)

        if not writer.write(self._qimage):
            raise RuntimeError(writer.errorString())


    def to_bytes(self, format, quality):
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)

        buffer.open(QBuffer.OpenModeFlag.WriteOnly)

        try:
            self.write(buffer, format, quality)

        finally:
            buffer.close()

        return byte_array


    def to_base64(self, format, quality):
        byte_array = self.to_bytes(format, quality)
        return byte_array.toBase64().data().decode("utf-8")


class LayerType(Enum):
    paint = "paintlayer"
    vector = "vectorlayer"
    group = "grouplayer"
    file = "filelayer"
    clone = "clonelayer"
    fill = "filllayer"
    filter = "filterlayer"
    transparency = "transparencymask"
    selection = "selectionmask"
    filtermask = "filtermask"
    transform = "transformmask"
    colorize = "colorizemask"

    def is_group(self):
        return self in (LayerType.group,)

    # Layers that contain color pixel data
    def is_image(self):
        return self in (
            LayerType.paint,
            LayerType.vector,
            LayerType.file,
            LayerType.clone,
            LayerType.filter,
            LayerType.fill,
        )

    # Layers that contain alpha pixel data
    def is_mask(self):
        return self in (LayerType.transparency, LayerType.selection)

    # Layers which modify their parent layer
    def is_filter(self):
        return self in (
            LayerType.transparency,
            LayerType.selection,
            LayerType.filtermask,
            LayerType.transform,
            LayerType.colorize,
        )


class Layer:
    def __init__(self, node):
        self._node = node


    @staticmethod
    def fromImage(document, name, image, x, y):
        layer = document.new_paint_layer(name)
        layer.write_image(image, x, y)
        return layer


    @property
    def id(self):
        return self._node.uniqueId().toString()

    @property
    def parent(self):
        return Layer(self._node.parentNode())

    @property
    def type(self):
        return LayerType(self._node.type())


    @property
    def name(self):
        return self._node.name()

    @name.setter
    def name(self, value):
        self._node.setName(value)


    @property
    def is_visible(self):
        return self._node.visible()

    @is_visible.setter
    def is_visible(self, value):
        self._node.setVisible(value)


    @property
    def is_locked(self):
        return self._node.locked()

    @is_locked.setter
    def is_locked(self, value):
        self._node.setLocked(value)


    def write_image(self, image, x, y):
        if not self._node.setPixelData(image.bytes(), x, y, image.width, image.height):
            raise RuntimeError("Writing image failed")


    def replace_image(self, image, x, y):
        self.write_image(image, x, y)
        self.crop(x, y, image.width, image.height)


    def move_to_top(self, parent):
        old_parent = self._node.parentNode()

        if old_parent is not None:
            old_parent.removeChildNode(self._node)

        parent._node.addChildNode(self._node, None)


    def remove(self):
        self._node.remove()


    def crop(self, x, y, width, height):
        self._node.cropNode(x, y, width, height)


    def insert_child(self, child, above=None):
        if above is None:
            self._node.addChildNode(child._node, None)
        else:
            self._node.addChildNode(child._node, above._node)


    # Iterates over the immediate children
    def children(self):
        for child in reversed(acquire_elements(self._node.childNodes())):
            yield Layer(child)


    # Iterates over all children, recursively
    def all_children(self):
        for child in self.children():
            yield child

            yield from child.all_children()


    def bounds(self):
        return Bounds.from_qrect(self._node.bounds())


    def image(self, bounds):
        assert self._node.colorDepth() == "U8", "Can only get the pixels of 8-bit images"

        data = self._node.projectionPixelData(bounds.x, bounds.y, bounds.width, bounds.height)

        assert data is not None and data.size() >= bounds.area() * 4

        return Image.from_packed_bytes(data, bounds.width, bounds.height)


# Many Pykrita functions return a `QList<QObject*>` where the objects are
# allocated for the caller. SIP does not handle this case and just leaks
# the objects outright. Fix this by taking explicit ownership of the objects.
# Note: ONLY call this if you are confident that the Pykrita function
# allocates the list members!
def acquire_elements(list):
    return list
    for obj in list:
        if obj is not None:
            sip.transferback(obj)
    return list

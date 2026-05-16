import krita
from pathlib import Path
from enum import Enum
from PyQt6 import sip
from typing import NamedTuple
from json import (dumps, loads)
import numpy as np
from . import clamp, round_to_multiple

from PyQt6.QtCore import QObject, QByteArray, QSize, QRect, QBuffer, QUuid, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPainter, QPixmap, QImage, QImageWriter


def get_extension(type):
    output = None

    for extension in Krita.extensions():
        if isinstance(extension, type):
            assert output is None
            output = extension

    assert output is not None
    return output


class LayerMetadata:
    def __init__(self, id, name, type):
        self.id = id
        self.name = name
        self.type = type

    def __eq__(self, other):
        return self.id == other.id and self.name == other.name and self.type == other.type


"""
    Manages the current document, notifies when it changes, and also notifies when layers change.
"""
class DocumentManager(QObject):
    document_changed = pyqtSignal()
    layers_changed = pyqtSignal()


    def __init__(self, parent):
        super().__init__(parent)

        self._document = None

        self.layers = []

        # Krita doesn't provide any way to be notified when the layers are changed,
        # so unfortunately we have to poll in order to detect changes.
        self._timer = QTimer(self)
        self._timer.start(500)
        self._timer.timeout.connect(self._update_layers)

        self.check_changes()


    def _get_all_layers(self):
        layers = []

        document = self._document

        if document is not None:
            root = document.root_layer()

            if root is not None:
                def loop(node, path):
                    for layer in node.children():
                        if layer.type.is_group() or layer.type.is_image():
                            child_path = path + [layer.name]
                            name = " ┊ ".join(child_path)

                            layers.append(LayerMetadata(layer.id, name, layer.type))

                            loop(layer, child_path)

                loop(root, [])

        return layers


    def _update_layers(self, emit=True):
        new_layers = self._get_all_layers()

        if self.layers != new_layers:
            self.layers = new_layers

            if emit:
                self.layers_changed.emit()


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


    def check_changes(self):
        document = Document.current()

        if not self.is_equal(document):
            self._document = document
            self._update_layers(False)
            self.document_changed.emit()


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


    def check_within_bounds(self, parent):
        assert self.x >= parent.x
        assert self.y >= parent.y
        assert self.width >= 0
        assert self.height >= 0
        assert (self.x + self.width) <= (parent.x + parent.width)
        assert (self.y + self.height) <= (parent.y + parent.height)
        return self


    def round_up(self, parent, multiple):
        assert multiple >= 1

        bounds = self.clamp_to_parent(parent)

        if multiple > 1:
            # Increases the bounds to the right and bottom
            width = round_to_multiple(bounds.width, multiple)
            height = round_to_multiple(bounds.height, multiple)

            parent_right = parent.x + parent.width
            parent_bottom = parent.y + parent.height

            # Clamp if it goes outside of the parent
            right = clamp(bounds.x + width, parent.x, parent_right)
            bottom = clamp(bounds.y + height, parent.y, parent_bottom)

            # If the bounds was clamped, increases the bounds to the left and top
            left = clamp(right - width, parent.x, parent_right)
            top = clamp(bottom - height, parent.y, parent_bottom)

            assert right >= left
            assert bottom >= top

            bounds = Bounds(left, top, right - left, bottom - top).check_within_bounds(parent)

        return bounds


    def clamp_to_parent(self, parent):
        parent_right = parent.x + parent.width
        parent_bottom = parent.y + parent.height

        x = clamp(self.x, parent.x, parent_right)
        y = clamp(self.y, parent.y, parent_bottom)
        width = clamp(self.width, 0, parent_right - x)
        height = clamp(self.height, 0, parent_bottom - y)

        return Bounds(x, y, width, height).check_within_bounds(parent)


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

    def __eq__(self, other):
        return self._selection == other._selection

    def __ne__(self, other):
        return self._selection != other._selection

    @staticmethod
    def solid(bounds, value):
        # TODO what about memory management? does this need to be manually deleted?
        selection = krita.Selection()
        # TODO is this the fastest way to create a selection that spans the entire document?
        selection.select(
            bounds.x,
            bounds.y,
            bounds.width,
            bounds.height,
            value,
        )
        return Selection(selection)

    def copy(self):
        return Selection(self._selection.duplicate())

    def add(self, other):
        self._selection.add(other._selection)

    def subtract(self, other):
        self._selection.subtract(other._selection)

    def invert(self):
        self._selection.invert()

    def smooth(self):
        self._selection.smooth()

    def grow(self, horizontal, vertical):
        self._selection.grow(horizontal, vertical)

    def shrink(self, horizontal, vertical):
        # TODO investigate the edgeLock argument
        self._selection.shrink(horizontal, vertical, False)


    def feather_outside(self, radius):
        # Hack needed because Krita feathers both inside and outside the selection
        half_grow = round(radius / 2)
        self.grow(half_grow, half_grow)

        # When Krita feathers a selection, it sometimes feathers a tiny
        # bit more than it's supposed to, so we compensate by feathering
        # a tiny bit less than the desired amount.
        half_feather = max(1, half_grow - 1)
        self._selection.feather(half_feather)

    # TODO this is off by 1 pixel when the radius is an odd number
    def feather_inside(self, radius):
        # Hack needed because Krita feathers both inside and outside the selection
        half = round(radius / 2)
        self.shrink(half, half)
        self._selection.feather(half)

    def feather_both(self, radius):
        self._selection.feather(radius)


    # TODO this is off by 1 pixel
    def border_outside(self, x, y):
        # Hack needed because Krita borders both inside and outside the selection
        half_x = round(x / 2)
        half_y = round(y / 2)
        self.grow(half_x, half_y)
        self._selection.border(half_x, half_y)

    # TODO this is off by 1 pixel
    def border_inside(self, x, y):
        # Hack needed because Krita borders both inside and outside the selection
        half_x = round(x / 2)
        half_y = round(y / 2)
        self.shrink(max(0, half_x - 1), max(0, half_y - 1))
        self._selection.border(half_x, half_y)

    # TODO this is off by 1 pixel
    def border_both(self, x, y):
        self._selection.border(x, y)


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


    def all_keys(self):
        return self._document.annotationTypes()

    def remove_key(self, key):
        self._document.removeAnnotation(key)


    def get_key_bytes(self, key, default=None):
        value = self._document.annotation(key)
        if value.size() > 0:
            return value
        return default

    def set_key_bytes(self, key, description, value: QByteArray):
        self._document.setAnnotation(key, description, value)


    def get_key_str(self, key, default=None):
        value = self.get_key_bytes(key)
        if value is not None:
            return value.data().decode("utf-8")
        return default

    def set_key_str(self, key, description, value: str):
        self.set_key_bytes(key, description, QByteArray(value.encode("utf-8")))


    def get_key_json(self, key, default=None):
        value = self.get_key_str(key)
        if value is not None:
            return loads(value)
        return default

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
                    return Image.from_krita_qimage(self._document.projection(bounds.x, bounds.y, bounds.width, bounds.height))

                finally:
                    if visible:
                        preview.is_visible = visible
                        self.refresh()

            else:
                self.refresh()
                #return Image.from_packed_bytes(self._document.pixelData(bounds.x, bounds.y, bounds.width, bounds.height), bounds.width, bounds.height)
                return Image.from_krita_qimage(self._document.projection(bounds.x, bounds.y, bounds.width, bounds.height))


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


    def check_format(self):
        assert self._qimage.format() == QImage.Format.Format_Grayscale8


    def is_solid(self, value):
        raw = Image(self._qimage).bytes()

        array = np.frombuffer(bytes(raw), dtype=np.uint8)

        return np.all(array == value)


    # TODO replace with base85
    def to_base64(self):
        return Image(self._qimage).to_base64()


class Image:
    def __init__(self, qimage: QImage):
        self._qimage = qimage


    @staticmethod
    def filename(name: str):
        return str(Path(__file__).parent.parent / "images" / name)


    @staticmethod
    def load_file(filename: str):
        path = Image.filename(filename)
        image = QImage()
        if not image.load(path):
            raise RuntimeError("Failed to load image {}", path)
        return Image(image)


    @staticmethod
    def from_qicon(qicon: QIcon, width, height, mode=QIcon.Mode.Normal, state=QIcon.State.Off):
        qimage = qicon.pixmap(QSize(width, height), mode, state).toImage()
        qimage.convertTo(QImage.Format.Format_ARGB32)
        return Image(qimage)


    # TODO replace with base85
    @staticmethod
    def from_base64(data: str, width, height):
        bytes = QByteArray.fromBase64(data.encode("utf-8"))
        return Image.from_packed_bytes(bytes, width, height, swap_rgb=True)


    @staticmethod
    def from_krita_qimage(qimage: QImage):
        # Krita uses BGR so we have to swap it to RGB
        qimage.rgbSwap()
        return Image(qimage)


    @staticmethod
    def from_packed_bytes(data: QByteArray, width, height, swap_rgb):
        assert data.size() == (width * height) * 4

        stride = width * 4
        qimage = QImage(data, width, height, stride, QImage.Format.Format_ARGB32)

        # Krita uses BGR so we have to swap it to RGB
        if swap_rgb:
            qimage.rgbSwap()

        return Image(qimage)


    @property
    def width(self):
        return self._qimage.width()

    @property
    def height(self):
        return self._qimage.height()

    def byte_size(self):
        return self._qimage.sizeInBytes()

    def bytes(self):
        ptr = self._qimage.constBits()
        return QByteArray(ptr.asstring(self._qimage.sizeInBytes()))


    def check_format(self):
        assert self._qimage.format() == QImage.Format.Format_ARGB32


    def scale_to_fit(self, width, height):
        scale = min(width / self.width, height / self.height)

        # Scale the width / height while keeping the same aspect ratio
        width = int(round(self.width * scale))
        height = int(round(self.height * scale))

        if self.width == width and self.height == height:
            return Image(self._qimage.copy())

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


    # TODO replace with base85
    def to_base64(self):
        return self.bytes().toBase64().data().decode("utf-8")


class LayerType(Enum):
    empty = ""
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

    def icon_name(self):
        match self:
            case LayerType.paint: return "paintLayer"
            case LayerType.vector: return "vectorLayer"
            case LayerType.group: return "groupLayer"
            case LayerType.file: return "fileLayer"
            case LayerType.clone: return "cloneLayer"
            case LayerType.fill: return "fillLayer"
            case LayerType.filter: return "filterLayer"
            case LayerType.transparency: return "transparencyMask"
            case LayerType.selection: return "selectionMask"
            case LayerType.filtermask: return "filterMask"
            case LayerType.transform: return "transformMask"
            case LayerType.colorize: return "colorizeMask"

    def icon(self):
        return Krita.icon(self.icon_name())

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

        return Image.from_packed_bytes(data, bounds.width, bounds.height, swap_rgb=True)


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

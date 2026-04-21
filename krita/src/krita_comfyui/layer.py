from enum import Enum
from PyQt6 import sip
from typing import NamedTuple

from PyQt6.QtCore import QByteArray, QRect, QBuffer
from PyQt6.QtGui import QImage, QImageWriter


class Bounds(NamedTuple):
    x: int
    y: int
    width: int
    height: int

    @staticmethod
    def from_qrect(qrect: QRect):
        return Bounds(qrect.x(), qrect.y(), qrect.width(), qrect.height())


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


class Image:
    def __init__(self, qimage: QImage):
        self._qimage = qimage


    @staticmethod
    def from_packed_bytes(data: QByteArray, width, height, channels=4):
        assert channels in {4, 1}
        stride = width * channels
        format = QImage.Format.Format_ARGB32 if channels == 4 else QImage.Format.Format_Grayscale8
        qimg = QImage(data, width, height, stride, format)
        return Image(qimg)


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


    @property
    def name(self):
        return self._node.name()


    @property
    def type(self):
        return LayerType(self._node.type())


    # Iterates over the immediate children
    def children(self):
        for child in reversed(acquire_elements(self._node.childNodes())):
            yield Layer(child)


    # Iterates over all children, recursively
    def all_children(self):
        for child in self.children():
            yield child

            yield from child.all_children()


    def find_layer(self, name):
        for child in self.all_children():
            if child.name == name:
                return child

        return None


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

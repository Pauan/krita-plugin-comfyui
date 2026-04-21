from enum import Enum
from PyQt6 import sip


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


# Many Pykrita functions return a `QList<QObject*>` where the objects are
# allocated for the caller. SIP does not handle this case and just leaks
# the objects outright. Fix this by taking explicit ownership of the objects.
# Note: ONLY call this if you are confident that the Pykrita function
# allocates the list members!
def acquire_elements(list):
    for obj in list:
        if obj is not None:
            sip.transferback(obj)
    return list

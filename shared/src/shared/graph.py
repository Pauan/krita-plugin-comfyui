import math
import base64
from typing import TypeAlias, TypedDict, Protocol


class Image(Protocol):
    width: int
    height: int

    def check_format(self):
        ...

    def to_base64(self) -> str:
        ...


class Mask(Image):
    def is_solid(self, value: int) -> bool:
        ...


NodeLink: TypeAlias = list[str | int]
NodeInput: TypeAlias = str | int | float | bool | NodeLink

class Node(TypedDict):
    class_type: str
    inputs: dict[str, NodeInput]


class ImageView:
    def __init__(self, ndarray):
        self._view = ndarray

    def width(self) -> int:
        return self._view.shape[1]

    def height(self) -> int:
        return self._view.shape[0]

    def to_base64(self) -> str:
        return base64.b64encode(self._view.tobytes()).decode(encoding="utf-8")


class MaskView:
    def __init__(self, ndarray):
        self._view = ndarray

    def width(self) -> int:
        return self._view.shape[1]

    def height(self) -> int:
        return self._view.shape[0]

    def to_base64(self) -> str:
        return base64.b64encode(self._view.tobytes()).decode(encoding="utf-8")

    def is_solid(self, value: int) -> bool:
        import numpy
        return numpy.all(self._view == value)


class NodeOutputs:
    def __init__(self, id: str):
        self.id = id

    def out(self, index: int) -> NodeLink:
        return [self.id, index]


class Graph:
    def __init__(self):
        self.node_id = 0
        self.cached_images = {}
        self.cached_masks = {}
        self.nodes: dict[str, Node] = {}


    def node_raw(self, class_type: str, **kwargs: NodeInput) -> NodeOutputs:
        id = str(self.node_id)
        self.node_id += 1

        self.nodes[id] = {
            "class_type": class_type,
            "inputs": kwargs,
        }

        return NodeOutputs(id)


    def convert_image(self, image: ImageView) -> NodeLink:
        base64 = image.to_base64()
        width = image.width()
        height = image.height()

        cached = self.cached_images.get((base64, width, height), None)

        if cached is None:
            cached = self.node_raw("krita_comfyui: LoadImageBase64", base64=base64, width=width, height=height).out(0)
            self.cached_images[(base64, width, height)] = cached

        return cached


    def convert_mask(self, mask: MaskView) -> NodeLink:
        base64 = mask.to_base64()
        width = mask.width()
        height = mask.height()

        cached = self.cached_masks.get((base64, width, height), None)

        if cached is None:
            # TODO figure out a faster way of determining if the selection is fully white or black
            if mask.is_solid(0xff):
                cached = self.node_raw("SolidMask", value=1.0, width=width, height=height).out(0)
            elif mask.is_solid(0x00):
                cached = self.node_raw("SolidMask", value=0.0, width=width, height=height).out(0)
            else:
                cached = self.node_raw("krita_comfyui: LoadMaskBase64", base64=base64, width=width, height=height).out(0)

            self.cached_masks[(base64, width, height)] = cached

        return cached


    def node(self, class_type: str, **kwargs: NodeInput) -> NodeOutputs:
        for key, value in kwargs.items():
            # TODO better detection for Image and Mask
            if isinstance(value, ImageView):
                kwargs[key] = self.convert_image(value)

            elif isinstance(value, MaskView):
                kwargs[key] = self.convert_mask(value)

        return self.node_raw(class_type, **kwargs)


    # Sends a list of stuff to ComfyUI
    def list(self, items: list[NodeInput]) -> NodeInput:
        return graph_list(self, items)


    # Causes an error to be thrown when evaluating the graph
    def error(self, message: str) -> NodeLink:
        return self.node("krita_comfyui: ThrowError", message=message).out(0)


    def dynamic_combo(self, prefix, dict):
        output = {}

        for key, value in dict.items():
            if key == prefix:
                output[key] = value
            else:
                output[f"{prefix}.{key}"] = value

        return output


    def finalize(self) -> dict[str, Node]:
        return self.nodes


    def debug(self) -> dict[str, Node]:
        output: dict[str, Node] = {}

        for key, value in self.nodes.items():
            match value["class_type"]:
                case "krita_comfyui: LoadImageBase64":
                    inputs = value["inputs"]
                    output[key] = {
                        "class_type": "krita_comfyui: LoadImageBase64",
                        "inputs": {
                            "base64": "...",
                            "width": inputs["width"],
                            "height": inputs["height"],
                        },
                    }

                case "krita_comfyui: LoadMaskBase64":
                    inputs = value["inputs"]
                    output[key] = {
                        "class_type": "krita_comfyui: LoadMaskBase64",
                        "inputs": {
                            "base64": "...",
                            "width": inputs["width"],
                            "height": inputs["height"],
                        },
                    }

                case _:
                    output[key] = value

        return output


# https://stackoverflow.com/a/2189827/449477
def digits(num: int) -> int:
    if num == 0:
        return 1
    else:
        return int(math.log10(num)) + 1


# TODO move this into ComfyUI
def graph_list(graph: Graph, items: list[NodeInput]) -> NodeInput:
    if len(items) == 1:
        return items[0]

    inputs: dict[str, NodeInput] = {}

    # We pad the numbers so that they are sorted correctly
    padding = digits(max(0, len(items) - 1))

    for i, value in enumerate(items):
        inputs["inputs.input" + str(i)] = value

    return graph.node("krita_comfyui: MakeList", **inputs).out(0)

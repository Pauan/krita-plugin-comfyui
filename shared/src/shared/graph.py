import math
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


class NodeOutputs:
    def __init__(self, id: str):
        self.id = id

    def out(self, index: int) -> NodeLink:
        return [self.id, index]


class Graph:
    def __init__(self):
        self.node_id = 0
        self.nodes: dict[str, Node] = {}


    def node(self, class_type: str, **kwargs: NodeInput) -> NodeOutputs:
        id = str(self.node_id)
        self.node_id += 1

        self.nodes[id] = {
            "class_type": class_type,
            "inputs": kwargs,
        }

        return NodeOutputs(id)


    # Sends a list of stuff to ComfyUI
    def list(self, items: list[NodeInput]) -> NodeInput:
        return graph_list(self, items)


    # Sends an Image to ComfyUI
    # Returns a tuple of (image, mask)
    def image(self, image: Image) -> tuple[NodeLink, NodeLink]:
        image.check_format()
        node = self.node("krita_comfyui: LoadImageBase64", base64=image.to_base64(), width=image.width, height=image.height)
        return (node.out(0), node.out(1))


    # Sends a Mask to ComfyUI
    def mask(self, mask: Mask) -> NodeLink:
        mask.check_format()

        # TODO figure out a faster way of determining if the selection is fully white
        if mask.is_solid(0xff):
            return self.node("SolidMask", value=1.0, width=mask.width, height=mask.height).out(0)
        else:
            return self.node("krita_comfyui: LoadMaskBase64", base64=mask.to_base64(), width=mask.width, height=mask.height).out(0)


    # Causes an error to be thrown when evaluating the graph
    def error(self, message: str) -> NodeLink:
        return self.node("krita_comfyui: ThrowError", message=message).out(0)


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
        inputs["inputs.input" + str(i).zfill(padding)] = value

    return graph.node("krita_comfyui: MakeList", **inputs).out(0)

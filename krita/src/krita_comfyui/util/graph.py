import math
from .. import shared


class Node:
    def __init__(self, id):
        self.id = id

    def out(self, index):
        return [self.id, index]


class Graph:
    def __init__(self):
        self.node_id = 0
        self.nodes = {}


    def node(self, class_type, **kwargs):
        id = str(self.node_id)
        self.node_id += 1

        self.nodes[id] = {
            "class_type": class_type,
            "inputs": kwargs,
        }

        return Node(id)


    # Sends a list of stuff to ComfyUI
    def list(self, items):
        return shared.graph_list(self, items)


    # Sends an Image to ComfyUI
    # Returns a tuple of (image, mask)
    def image(self, image):
        image.check_format()
        node = self.node("krita_comfyui: LoadImageBase64", base64=image, width=image.width, height=image.height)
        return (node.out(0), node.out(1))


    # Sends a Mask to ComfyUI
    def mask(self, mask):
        mask.check_format()

        # TODO figure out a faster way of determining if the selection is fully white
        if mask.is_solid(0xff):
            return self.node("SolidMask", value=1.0, width=mask.width, height=mask.height).out(0)
        else:
            return self.node("krita_comfyui: LoadMaskBase64", base64=mask, width=mask.width, height=mask.height).out(0)


    # Causes an error to be thrown when evaluating the graph
    def error(self, message):
        return self.node("krita_comfyui: ThrowError", message=message).out(0)


    def finalize(self):
        output = self.nodes

        self.nodes = None

        # Converting images to base64 is expensive, so we delay it until now.
        for value in output.values():
            match value["class_type"]:
                case "krita_comfyui: LoadImageBase64" | "krita_comfyui: LoadMaskBase64":
                    inputs = value["inputs"]

                    base64 = inputs["base64"]

                    if not isinstance(base64, str):
                        inputs["base64"] = base64.to_base64()

        return output


    def debug(self):
        output = {}

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

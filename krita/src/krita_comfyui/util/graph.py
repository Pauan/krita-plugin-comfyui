import math


# https://stackoverflow.com/a/2189827/449477
def digits(num):
    if num == 0:
        return 1
    else:
        return int(math.log10(num)) + 1


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
        if len(items) == 1:
            return items[0]

        inputs = {}

        # We pad the numbers so that they are sorted correctly
        padding = digits(max(0, len(items) - 1))

        for i, value in enumerate(items):
            inputs["inputs.input" + str(i).zfill(padding)] = value

        return self.node("CreateList", **inputs).out(0)


    # Sends an Image to ComfyUI
    # Returns a tuple of (image, mask)
    def image(self, image):
        image.check_format()
        node = self.node("krita_comfyui: LoadImageBase64", base64=image.to_base64(), width=image.width, height=image.height)
        return (node.out(0), node.out(1))


    # Sends a Mask to ComfyUI
    def mask(self, mask):
        mask.check_format()
        return self.node("krita_comfyui: LoadMaskBase64", base64=mask.to_base64(), width=mask.width, height=mask.height).out(0)


    # Causes an error to be thrown when evaluating the graph
    def error(self, message):
        return self.node("krita_comfyui: ThrowError", message=message).out(0)


    def serialize(self):
        return self.nodes


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

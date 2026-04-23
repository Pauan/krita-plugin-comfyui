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


    @staticmethod
    def from_serialized(nodes):
        node_id = 0

        for key in nodes.keys():
            try:
                node_id = max(node_id, int(key) + 1)
            except:
                pass

        graph = Graph()
        graph.node_id = node_id
        graph.nodes = nodes
        return graph


    def node(self, name, **kwargs):
        id = str(self.node_id)
        self.node_id += 1

        self.nodes[id] = {
            "class_type": name,
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
    # Returns an (image, mask) tuple
    def image(self, image):
        node = self.node("krita_comfyui: LoadImageBase64", base64=image.to_base64("png", 9))
        return (node.out(0), node.out(1))


    # Normally you can just pass in boolean directly, but you can use this
    # if you need a node so you can link it to other nodes.
    def boolean(self, value):
        return self.node("PrimitiveBoolean", value=value).out(0)


    # Normally you can just pass in int directly, but you can use this
    # if you need a node so you can link it to other nodes.
    def int(self, value):
        return self.node("PrimitiveInt", value=value).out(0)


    def serialize(self):
        return self.nodes


def krita_selection(document):
    bounds = document.bounds()

    selection = document.selection()

    if selection is not None:
        selection = selection.clamp_to_parent(bounds)
    else:
        selection = bounds

    return (
        selection != bounds,
        selection.x,
        selection.y,
        selection.width,
        selection.height,
    )


def krita_canvas(document):
    bounds = document.bounds()

    image = document.canvas(bounds)

    return (image, bounds.width, bounds.height)


def krita_layers(document, name, mode):
    layers = []

    bounds = document.bounds()

    layer = document.find_layer_by_name(name)

    if layer is None:
        raise RuntimeError("Could not find layer {}".format(name))

    def add_image(layer):
        layers.append((layer.name, layer.image(bounds)))

    if mode == "individual":
        if layer.type.is_image():
            add_image(layer)

        for child in layer.all_children():
            if child.type.is_image():
                add_image(child)

    elif mode == "flatten":
        if layer.type.is_image() or layer.type.is_group():
            add_image(layer)

    else:
        raise RuntimeError("mode must be individual or flatten")

    return layers


class ConvertGraph:
    def __init__(self, document, graph):
        self.document = document

        self.selection = None
        self.canvas = None
        self.layers = {}

        self.replaced_links = {}

        self.graph = graph


    def get_selection(self):
        if self.selection is None:
            (active, x, y, width, height) = krita_selection(self.document)

            self.selection = (
                self.graph.boolean(active),
                self.graph.int(x),
                self.graph.int(y),
                self.graph.int(width),
                self.graph.int(height),
            )

        return self.selection


    def get_canvas(self):
        if self.canvas is None:
            (image, width, height) = krita_canvas(self.document)

            (image, mask) = self.graph.image(image)

            self.canvas = (
                image,
                mask,
                self.graph.int(width),
                self.graph.int(height),
            )

        return self.canvas


    def get_layers(self, name, mode):
        layers = self.layers.get((name, mode), None)

        if layers is None:
            images = []
            masks = []
            names = []

            for (name, image) in krita_layers(self.document, name, mode):
                (image, mask) = self.graph.image(image)

                images.append(image)
                masks.append(mask)
                names.append(name)

            layers = (
                self.graph.list(images),
                self.graph.list(masks),
                self.graph.list(names),
            )

            self.layers[(name, mode)] = layers

        return layers


    def replace_output_links(id, values):
        for index, value in enumerated(values):
            self.replaced_links[(id, index)] = value


    def convert(self):
        deleted = []

        for id, node in self.graph.nodes.items():
            match node["class_type"]:
                case "krita_comfyui: KritaSelection":
                    self.replace_output_links(id, self.get_selection())
                    deleted.append(id)

                case "krita_comfyui: KritaCanvas":
                    self.replace_output_links(id, self.get_canvas())
                    deleted.append(id)

                case "krita_comfyui: KritaLayers":
                    inputs = node["inputs"]
                    self.replace_output_links(id, self.get_layers(inputs["name"], inputs["mode"]))
                    deleted.append(id)

        for id in deleted:
            del self.graph.nodes[id]


    def replace_links(self):
        for node in self.graph.nodes.values():
            inputs = node["inputs"]

            for key, value in inputs.items():
                if isinstance(value, list) and len(value) == 2:
                    replacement = self.replaced_links.get((value[0], value[1]), None)

                    if replacement is not None:
                        inputs[key] = replacement

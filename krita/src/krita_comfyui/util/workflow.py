import random
import sys
from .graph import Graph
from .krita import Mask


def is_link(value):
    return isinstance(value, list) and len(value) == 2


def zip_inputs(*inputs):
    max_length = max(len(x) for x in inputs)

    for index in range(max_length):
        output = tuple(
            input[min(index, len(input) - 1)]
            for input
            in inputs
        )

        yield output


class WorkflowError(RuntimeError):
    pass


class Workflow:
    def __init__(self, document, json, seed, ui_values):
        self.document = document
        self.json = json
        self.seed = seed
        self.ui_values = ui_values

        self.graph = Graph()

        self.node_ids = []
        self.replaced_links = {}
        self.replaced_ids = {}

        self.document_bounds = self.document.bounds()
        self.canvas = None
        self.selection = None
        self.layers = {}
        self.layer_image = {}

        self.const_nodes = {
            "krita_comfyui: KritaUiFloat": self.evaluate_ui,
            "krita_comfyui: KritaUiInt": self.evaluate_ui,
            "krita_comfyui: KritaUiBoolean": self.evaluate_ui,
            "krita_comfyui: KritaUiString": self.evaluate_ui,
            "krita_comfyui: KritaUiLayerId": self.evaluate_ui,
            "krita_comfyui: KritaUiCombo": self.evaluate_ui,
        }


    @staticmethod
    def random_seed():
        # https://github.com/Comfy-Org/ComfyUI/blob/ed201fff08fbbd3dbcc500b252a9f41e8051c256/nodes.py#L1570
        # https://github.com/Comfy-Org/ComfyUI/blob/ed201fff08fbbd3dbcc500b252a9f41e8051c256/comfy_extras/nodes_primitive.py#L52
        return random.randint(0, sys.maxsize)


    def get_ui_values(self, id):
        try:
            return self.ui_values[id]
        except KeyError:
            raise WorkflowError("UI id {} not found".format(id))


    def replace_outputs(self, id, outputs):
        for index, output in enumerate(outputs):
            self.replaced_links[(id, index)] = output


    def replace_id(self, old_id, node):
        self.node_ids.append(node.id)
        self.replaced_ids[old_id] = node.id


    def evaluate_ui(self, node):
        ui_id = node["inputs"]["id"]
        values = self.get_ui_values(ui_id)
        assert isinstance(values, list)
        return (values, [x != "" for x in values])


    # Evaluates the link if the connected node has a constant value.
    #
    # Returns a tuple:
    #
    #   1. True if it was constant.
    #   2. List of values.
    def evaluate_link(self, value):
        # If it's a node link, then follow the link.
        if is_link(value):
            node = self.json[value[0]]
            name = node["class_type"]

            try:
                f = self.const_nodes[name]
            except KeyError:
                # If the node isn't constant, return the link as-is
                return (False, [value])

            outputs = f(node)
            value = outputs[value[1]]
            assert isinstance(value, list)
            return (True, value)

        else:
            return (False, [value])


    def get_canvas(self):
        if self.canvas is None:
            image = self.document.canvas(self.document_bounds)

            (image, mask) = self.graph.image(image)

            self.canvas = (
                image,
                mask,
                self.document_bounds.width,
                self.document_bounds.height,
            )

        return self.canvas


    def get_selection(self):
        if self.selection is None:
            selection = self.document.selection()

            if selection is not None:
                selection_bounds = selection.bounds().clamp_to_parent(self.document_bounds)
                mask = selection.mask(self.document_bounds)

                if selection_bounds == self.document_bounds:
                    active = not mask.is_solid(0xff)
                else:
                    active = True

            else:
                selection_bounds = self.document_bounds
                mask = Mask.solid(0xff, self.document_bounds.width, self.document_bounds.height)
                active = False

            mask = self.graph.mask(mask)

            self.selection = (
                active,
                mask,
                selection_bounds.x,
                selection_bounds.y,
                selection_bounds.width,
                selection_bounds.height,
            )

        return self.selection


    def get_layer_image(self, layer):
        image = self.layer_image.get(layer.id, None)

        if image is None:
            image = self.graph.image(layer.image(self.document_bounds))
            self.layer_image[layer.id] = image

        return image


    def get_layers(self, layer_id, mode):
        layers = self.layers.get((layer_id, mode), None)

        if layers is None:
            images = []
            masks = []
            names = []

            layer = self.document.find_layer_by_id(layer_id)

            if layer is None:
                raise WorkflowError("Could not find layer {}".format(layer_id))

            def add_image(layer):
                (image, mask) = self.get_layer_image(layer)
                images.append(image)
                masks.append(mask)
                names.append(layer.name)

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
                raise WorkflowError("mode must be individual or flatten")

            layers = (images, masks, names)
            self.layers[(layer_id, mode)] = layers

        return layers


    def process_node(self, id, node):
        class_type = node["class_type"]

        match class_type:
            case "krita_comfyui: KritaCanvas":
                self.replace_outputs(id, self.get_canvas())

            case "krita_comfyui: KritaSelection":
                self.replace_outputs(id, self.get_selection())

            case "krita_comfyui: KritaSeed":
                self.replace_outputs(id, (self.seed,))


            # @TODO maybe cache this based on inputs somehow ?
            case "krita_comfyui: KritaLayers":
                inputs = node["inputs"]

                images = []
                masks = []
                names = []

                (_, layer_id) = self.evaluate_link(inputs["layer_id"])
                (_, mode) = self.evaluate_link(inputs["mode"])

                error = None

                for (layer_id, mode) in zip_inputs(layer_id, mode):
                    if not isinstance(layer_id, str):
                        raise WorkflowError("[#{} Krita Layers]\nlayer_id must be a string constant".format(id))

                    if not isinstance(mode, str):
                        raise WorkflowError("[#{} Krita Layers]\nmode must be a string constant".format(id))

                    # If the layer name is empty, throw an error
                    if layer_id == "":
                        if error is None:
                            error = self.graph.error("[#{} Krita Layers]\nlayer_id is empty".format(id))
                        images.append(error)
                        masks.append(error)
                        names.append(error)

                    else:
                        layers = self.get_layers(layer_id, mode)
                        images.extend(layers[0])
                        masks.extend(layers[1])
                        names.extend(layers[2])

                self.replace_outputs(id, (
                    self.graph.list(images),
                    self.graph.list(masks),
                    self.graph.list(names),
                ))


            case _:
                self.replace_id(id, self.graph.node(class_type, **node["inputs"]))


    def replace_input(self, value):
        (is_const, const_value) = self.evaluate_link(value)

        if is_const:
            return self.graph.list(const_value)

        if is_link(value):
            try:
                new_id = self.replaced_ids[value[0]]
                return [new_id, value[1]]
            except KeyError:
                pass

            try:
                return self.replaced_links[(value[0], value[1])]
            except KeyError:
                pass

        return value


    def to_graph(self):
        for id, node in self.json.items():
            # We skip const nodes completely, they're evaluated by `evaluate_link`
            if not node["class_type"] in self.const_nodes:
                self.process_node(id, node)

        for id in self.node_ids:
            node = self.graph.nodes[id]

            inputs = {}

            for key, value in node["inputs"].items():
                inputs[key] = self.replace_input(value)

            node["inputs"] = inputs

        return self.graph

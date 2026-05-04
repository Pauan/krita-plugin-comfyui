import random
import sys
from ..util.graph import Graph
from ..util.krita import Selection


def is_link(value):
    return isinstance(value, list) and len(value) == 2


def zip_lists(inputs):
    max_length = max(len(x) for x in inputs)

    for index in range(max_length):
        output = tuple(
            input[min(index, len(input) - 1)]
            for input
            in inputs
        )

        yield output

def zip_inputs(*inputs):
    yield from zip_lists([x.values for x in inputs])


class WorkflowError(RuntimeError):
    pass


class Link:
    def __init__(self, values):
        assert isinstance(values, list)

        # List of values
        self.values = values

        self.node = None

    # Converts the Link into a graph node.
    #
    # This is cached, so calling it multiple times gives the same node.
    def to_node(self, graph):
        if self.node is None:
            self.node = graph.list(self.values)
        return self.node


class UiLink(Link):
    def __init__(self, values, id):
        super().__init__(values)
        self.id = id


# Evaluates a UI widget to a constant value
class KritaUi:
    def __init__(self, ui_values, type):
        self.ui_values = ui_values
        self.type = type


    def get_values(self, id):
        id = f"{self.type}/{id}"
        try:
            return self.ui_values[id]
        except KeyError:
            raise WorkflowError(f"UI widget [{id}] not found")


    def get_outputs(self, workflow, node_id, node):
        id = node["inputs"]["id"]
        values = self.get_values(id)

        return (
            UiLink(values, id),
            UiLink([x != "" for x in values], id),
        )


class KritaSelection:
    def __init__(self):
        self.selection = None

    def get_outputs(self, workflow, node_id, node):
        if self.selection is None:
            bounds = workflow.bounds()

            selection = workflow.document.selection()

            if selection is None:
                selection = Selection.solid(bounds, 0xff)
                active = False

            else:
                if selection.bounds() == bounds:
                    # TODO figure out a faster way of determining if the selection is fully white
                    active = not selection.mask(bounds).is_solid(0xff)
                else:
                    active = True

            self.selection = (
                Link([selection]),
                Link([active]),
            )

        return self.selection


class KritaSelectionBorder:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        selection = workflow.evaluate_link(inputs["selection"])
        x = workflow.evaluate_link(inputs["x"])
        y = workflow.evaluate_link(inputs["y"])

        outputs = []

        for selection, x, y in zip_inputs(selection, x, y):
            assert isinstance(selection, Selection)

            if not isinstance(x, int):
                raise WorkflowError(f"[#{node_id} Krita Selection: Border]\nx must be an int constant")

            if not isinstance(y, int):
                raise WorkflowError(f"[#{node_id} Krita Selection: Border]\ny must be an int constant")

            if x == 0 and y == 0:
                outputs.append(selection)

            else:
                new_selection = selection.copy()
                new_selection.border(x, y)
                #new_selection.subtract(selection)
                outputs.append(new_selection)

        return (
            Link(outputs),
        )


class KritaSelectionBounds:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        selection = workflow.evaluate_link(inputs["selection"])

        x = []
        y = []
        width = []
        height = []

        for selection in selection.values:
            assert isinstance(selection, Selection)

            bounds = selection.bounds().clamp_to_parent(workflow.bounds())
            x.append(bounds.x)
            y.append(bounds.y)
            width.append(bounds.width)
            height.append(bounds.height)

        return (
            Link(x),
            Link(y),
            Link(width),
            Link(height),
        )


class KritaSelectionFeather:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        selection = workflow.evaluate_link(inputs["selection"])
        amount = workflow.evaluate_link(inputs["amount"])
        mode = workflow.evaluate_link(inputs["mode"])

        outputs = []

        for selection, amount, mode in zip_inputs(selection, amount, mode):
            assert isinstance(selection, Selection)

            if not isinstance(amount, int):
                raise WorkflowError(f"[#{node_id} Krita Selection: Feather]\namount must be an int constant")

            if not isinstance(mode, str):
                raise WorkflowError(f"[#{node_id} Krita Selection: Feather]\nmode must be a string constant")

            if amount == 0:
                outputs.append(selection)

            elif mode == "outside":
                new_selection = selection.copy()
                new_selection.grow(amount, amount)

                # When Krita feathers a selection, it sometimes feathers a tiny
                # bit more than it's supposed to, so we compensate by feathering
                # a tiny bit less than the desired amount.
                new_selection.feather(max(min(2, amount), amount - 2))

                # This guarantees that the original selection will always be
                # white. This prevents the feathering from bleeding into the
                # original selection.
                new_selection.add(selection)
                outputs.append(new_selection)

            elif mode == "inside":
                new_selection = selection.copy()
                new_selection.feather(amount)
                outputs.append(new_selection)

            else:
                raise WorkflowError(f"[#{node_id} Krita Selection: Feather]\nmode must outside or inside")

        return (
            Link(outputs),
        )


class KritaSelectionGrow:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        selection = workflow.evaluate_link(inputs["selection"])
        x = workflow.evaluate_link(inputs["x"])
        y = workflow.evaluate_link(inputs["y"])

        outputs = []

        for selection, x, y in zip_inputs(selection, x, y):
            assert isinstance(selection, Selection)

            if not isinstance(x, int):
                raise WorkflowError(f"[#{node_id} Krita Selection: Grow]\nx must be an int constant")

            if not isinstance(y, int):
                raise WorkflowError(f"[#{node_id} Krita Selection: Grow]\ny must be an int constant")

            if x == 0 and y == 0:
                outputs.append(selection)

            else:
                selection = selection.copy()
                selection.grow(x, y)
                outputs.append(selection)

        return (
            Link(outputs),
        )


class KritaSelectionInvert:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        selection = workflow.evaluate_link(inputs["selection"])

        outputs = []

        for selection in selection.values:
            assert isinstance(selection, Selection)
            selection = selection.copy()
            selection.invert()
            outputs.append(selection)

        return (
            Link(outputs),
        )


class KritaSelectionMask:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        selection = workflow.evaluate_link(inputs["selection"])

        outputs = []

        for selection in selection.values:
            assert isinstance(selection, Selection)
            mask = selection.mask(workflow.bounds())
            mask = workflow.graph.mask(mask)
            outputs.append(mask)

        return (
            Link(outputs),
        )


class KritaSelectionShrink:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        selection = workflow.evaluate_link(inputs["selection"])
        x = workflow.evaluate_link(inputs["x"])
        y = workflow.evaluate_link(inputs["y"])

        outputs = []

        for selection, x, y in zip_inputs(selection, x, y):
            assert isinstance(selection, Selection)

            if not isinstance(x, int):
                raise WorkflowError(f"[#{node_id} Krita Selection: Shrink]\nx must be an int constant")

            if not isinstance(y, int):
                raise WorkflowError(f"[#{node_id} Krita Selection: Shrink]\ny must be an int constant")

            if x == 0 and y == 0:
                outputs.append(selection)

            else:
                selection = selection.copy()
                selection.shrink(x, y)
                outputs.append(selection)

        return (
            Link(outputs),
        )


class KritaSelectionSmooth:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        selection = workflow.evaluate_link(inputs["selection"])

        outputs = []

        for selection in selection.values:
            assert isinstance(selection, Selection)
            selection = selection.copy()
            selection.smooth()
            outputs.append(selection)

        return (
            Link(outputs),
        )


class KritaCanvas:
    def __init__(self):
        self.canvas = None

    def get_outputs(self, workflow, node_id, node):
        if self.canvas is None:
            bounds = workflow.bounds()

            image = workflow.document.canvas(bounds)

            (image, mask) = workflow.graph.image(image)

            self.canvas = (
                Link([image]),
                Link([mask]),
                Link([bounds.width]),
                Link([bounds.height]),
            )

        return self.canvas


class KritaLayers:
    def __init__(self):
        self.layers = {}
        self.layer_image = {}


    def get_layer_image(self, workflow, layer):
        image = self.layer_image.get(layer.id, None)

        if image is None:
            image = workflow.graph.image(layer.image(workflow.bounds()))
            self.layer_image[layer.id] = image

        return image


    def get_layers(self, workflow, layer_id, mode):
        layers = self.layers.get((layer_id, mode), None)

        if layers is None:
            images = []
            masks = []
            names = []

            layer = workflow.document.find_layer_by_id(layer_id)

            if layer is None:
                raise WorkflowError(f"Could not find layer {layer_id}")

            def add_image(layer):
                (image, mask) = self.get_layer_image(workflow, layer)
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


    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        images = []
        masks = []
        names = []

        layer_id_link = workflow.evaluate_link(inputs["layer_id"])
        mode_link = workflow.evaluate_link(inputs["mode"])

        error = None

        for (layer_id, mode) in zip_inputs(layer_id_link, mode_link):
            if not isinstance(layer_id, str):
                raise WorkflowError(f"[#{node_id} Krita Layers]\nlayer_id must be a string constant")

            if not isinstance(mode, str):
                raise WorkflowError(f"[#{node_id} Krita Layers]\nmode must be a string constant")

            # If the layer name is empty, throw an error
            if layer_id == "":
                if error is None:
                    # TODO maybe raise the error immediately?
                    if isinstance(layer_id_link, UiLink):
                        error = workflow.graph.error(f"Layer selector [{layer_id_link.id}] is empty")
                    else:
                        error = workflow.graph.error(f"[#{node_id} Krita Layers]\nlayer_id is empty")

                images.append(error)
                masks.append(error)
                names.append(error)

            else:
                layers = self.get_layers(workflow, layer_id, mode)
                images.extend(layers[0])
                masks.extend(layers[1])
                names.extend(layers[2])

        return (
            Link(images),
            Link(masks),
            Link(names),
        )


class KritaSeed:
    def get_outputs(self, workflow, node_id, node):
        return (
            Link([workflow.seed]),
        )


class Switch:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        switch = workflow.evaluate_link(inputs["switch"])
        on_true = workflow.evaluate_link(inputs["on_true"])
        on_false = workflow.evaluate_link(inputs["on_false"])

        outputs = []

        for (switch, on_true, on_false) in zip_inputs(switch, on_true, on_false):
            if isinstance(switch, bool):
                if switch:
                    outputs.append(on_true)
                else:
                    outputs.append(on_false)

            # We don't know if switch is true or false, so we create
            # a node and determine the branch at runtime.
            else:
                outputs.append(workflow.graph.node("ComfySwitchNode",
                    switch=switch,
                    # Even though we don't know which branch to take,
                    # the branches are still constant-evaluated.
                    on_false=on_false,
                    on_true=on_true,
                ).out(0))

        return (
            Link(outputs),
        )


class WorkflowGraph:
    def __init__(self, document, json, seed, ui_values):
        self.document = document
        self.json = json
        self.seed = seed

        self.graph = Graph()

        self.cached_bounds = None

        # The cached depth of each node.
        self.node_depths = {}

        # When we copy an existing node, we have to replace the old node ID with the new node ID.
        self.replaced_ids = {}

        # Cached outputs for constant-evaluated nodes.
        self.const_outputs = {}

        # The node IDs which can be constant evaluated.
        self.const_nodes = {
            "krita_comfyui: KritaUiBoolean": KritaUi(ui_values, "boolean"),
            "krita_comfyui: KritaUiCombo": KritaUi(ui_values, "combo"),
            "krita_comfyui: KritaUiFloat": KritaUi(ui_values, "float"),
            "krita_comfyui: KritaUiInt": KritaUi(ui_values, "int"),
            "krita_comfyui: KritaUiLayerId": KritaUi(ui_values, "layer_id"),
            "krita_comfyui: KritaUiString": KritaUi(ui_values, "string"),

            "krita_comfyui: KritaCanvas": KritaCanvas(),
            "krita_comfyui: KritaLayers": KritaLayers(),
            "krita_comfyui: KritaSeed": KritaSeed(),

            "krita_comfyui: KritaSelection": KritaSelection(),
            "krita_comfyui: KritaSelectionBorder": KritaSelectionBorder(),
            "krita_comfyui: KritaSelectionBounds": KritaSelectionBounds(),
            "krita_comfyui: KritaSelectionFeather": KritaSelectionFeather(),
            "krita_comfyui: KritaSelectionGrow": KritaSelectionGrow(),
            "krita_comfyui: KritaSelectionInvert": KritaSelectionInvert(),
            "krita_comfyui: KritaSelectionMask": KritaSelectionMask(),
            "krita_comfyui: KritaSelectionShrink": KritaSelectionShrink(),
            "krita_comfyui: KritaSelectionSmooth": KritaSelectionSmooth(),

            "ComfySwitchNode": Switch(),
        }


    def bounds(self):
        if self.cached_bounds is None:
            self.cached_bounds = self.document.bounds()
        return self.cached_bounds


    @staticmethod
    def random_seed():
        # https://github.com/Comfy-Org/ComfyUI/blob/ed201fff08fbbd3dbcc500b252a9f41e8051c256/nodes.py#L1570
        # https://github.com/Comfy-Org/ComfyUI/blob/ed201fff08fbbd3dbcc500b252a9f41e8051c256/comfy_extras/nodes_primitive.py#L52
        return random.randint(0, sys.maxsize)


    # Evaluates the link if the connected node has a constant value.
    def evaluate_link(self, value):
        # If it's a node link, then follow the link.
        if is_link(value):
            node_id = value[0]

            try:
                # If we've evaluated this node before, return the cached outputs.
                outputs = self.const_outputs[node_id]

            # We haven't evaluated this node before.
            except KeyError:
                node = self.json[node_id]
                name = node["class_type"]

                try:
                    const_node = self.const_nodes[name]

                # The node isn't constant, that means it's a link to an old node,
                # so we replace its ID with the new ID.
                except KeyError:
                    # TODO cache this in const_outputs somehow ?
                    new_id = self.replaced_ids[node_id]
                    value = [new_id, value[1]]
                    return Link([value])

                outputs = const_node.get_outputs(self, node_id, node)
                self.const_outputs[node_id] = outputs

            return outputs[value[1]]

        else:
            return Link([value])


    def find_depth(self, node_id):
        try:
            max_depth = self.node_depths[node_id]

        except KeyError:
            max_depth = 0

            node = self.json[node_id]

            for value in node["inputs"].values():
                if is_link(value):
                    link_id = value[0]
                    depth = self.find_depth(link_id)
                    max_depth = max(max_depth, depth + 1)

            self.node_depths[node_id] = max_depth

        return max_depth


    # Returns a graph which contains a copy of all the old nodes, except
    # constant evaluated nodes have been removed and replaced with their
    # constant outputs.
    def evaluate(self):
        copied_nodes = []


        for id, node in self.json.items():
            class_type = node["class_type"]

            # We skip const nodes completely, they're evaluated by `evaluate_link`
            if not class_type in self.const_nodes:
                depth = self.find_depth(id)

                # We create a new node which is the same as the old node.
                new_node = self.graph.node(class_type, **node["inputs"])

                # We only process the copied nodes, any other nodes which are created
                # by constant evaluation (images, lists, etc.) won't be touched.
                copied_nodes.append((depth, new_node.id))

                # We have to replace the old node ID with the new node ID.
                self.replaced_ids[id] = new_node.id


        # We evaluate the deepest nodes first, so that way if a Switch is
        # encountered it can do proper dead code elimination of any
        # branches that aren't taken.
        copied_nodes.sort(key=lambda x: x[0], reverse=True)

        for (depth, name) in [(depth, self.graph.nodes[id]["class_type"]) for (depth, id) in copied_nodes]:
            print(depth, name)


        # For all of the copied nodes, we have to constant-evaluate their
        # inputs.
        #
        # We do this in a second pass because we need to evaluate them in
        # the right order (deepest node first) and also we have to replace
        # the old IDs with new IDs from replaced_ids.
        for _, id in copied_nodes:
            node = self.graph.nodes[id]

            inputs = {}

            for key, value in node["inputs"].items():
                inputs[key] = self.evaluate_link(value).to_node(self.graph)

            node["inputs"] = inputs


        return self.graph

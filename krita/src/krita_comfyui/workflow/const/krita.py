# This module contains constant-evaluation versions of the Krita nodes.
from . import WorkflowError, Link, zip_inputs, check_booleans
from ...util.krita import Bounds


def crop_to_bounds(node_id, name, values):
    for crop in values:
        if not isinstance(crop, dict):
            raise WorkflowError(f"[#{node_id} {name}]\ncrop must be a constant bounding box")

        yield Bounds.from_json(crop)


def evaluate_crop_link(workflow, node_id, name, inputs, default):
    crop = inputs.get("crop", None)

    if crop is None:
        return Link([default])
    else:
        return Link(list(crop_to_bounds(node_id, name, workflow.evaluate_link(crop).values)))


class UiLink(Link):
    def __init__(self, values, ids):
        super().__init__(values)
        self.ids = ids


# Evaluates a UI widget to a constant value
class KritaUi:
    def __init__(self, type, outputs):
        self.type = type
        self.outputs = outputs

    def get_id(self, id):
        return f"{self.type}/{id}"

    def get_outputs(self, workflow, node_id, node):
        ids = []
        links = tuple(UiLink([], ids) for _ in self.outputs)

        for id in workflow.evaluate_link(node["inputs"]["id"]).values:
            id = self.get_id(id)
            values = workflow.get_ui_values(id)

            ids.append(id)

            for link, key in zip(links, self.outputs):
                link.values.extend(value[key] for value in values)

        return links


class KritaCanvas:
    def get_outputs(self, workflow, node_id, node):
        outputs = (
            Link([]),
            Link([]),
            Link([]),
            Link([]),
        )

        bounds = workflow.bounds()

        for crop in evaluate_crop_link(workflow, node_id, "Krita Canvas", node["inputs"], bounds).values:
            cached_canvas = workflow.cached_canvas.get(crop, None)

            if cached_canvas is None:
                image = workflow.document.canvas(crop)
                (image, mask) = workflow.graph.image(image)
                cached_canvas = (image, mask, bounds.width, bounds.height)
                workflow.cached_canvas[crop] = cached_canvas

            assert len(outputs) == len(cached_canvas)

            for output, value in zip(outputs, cached_canvas):
                output.values.append(value)

        return outputs


class KritaDebug:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        enabled = workflow.evaluate_link(inputs["enabled"])

        (all_true, all_false) = check_booleans(enabled.values)

        # If it's disabled, don't evaluate anything.
        if all_false and not all_true:
            return ()

        else:
            outputs = {}

            for key, value in inputs.items():
                if key == "enabled":
                    outputs[key] = enabled.to_node(workflow.graph)
                else:
                    outputs[key] = workflow.evaluate_link(value).to_node(workflow.graph)

            workflow.graph.node("krita_comfyui: KritaDebug", **outputs)

            return ()


class KritaLayers:
    def get_layer_image(self, workflow, layer, crop):
        image = workflow.cached_layer_images.get((layer.id, crop), None)

        if image is None:
            image = workflow.graph.image(layer.image(crop))
            workflow.cached_layer_images[(layer.id, crop)] = image

        return image


    def get_layers(self, workflow, layer_id, crop, mode):
        layers = workflow.cached_layers.get((layer_id, crop, mode), None)

        if layers is None:
            images = []
            masks = []
            names = []

            layer = workflow.document.find_layer_by_id(layer_id)

            if layer is None:
                raise WorkflowError(f"Could not find layer {layer_id}")

            def add_image(layer):
                (image, mask) = self.get_layer_image(workflow, layer, crop)
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
            workflow.cached_layers[(layer_id, crop, mode)] = layers

        return layers


    def get_outputs(self, workflow, node_id, node):
        bounds = workflow.bounds()
        inputs = node["inputs"]

        images = []
        masks = []
        names = []

        layer_id_link = workflow.evaluate_link(inputs["layer_id"])
        crop = evaluate_crop_link(workflow, node_id, "Krita Layers", inputs, bounds)
        mode_link = workflow.evaluate_link(inputs["mode"])

        error = None

        for layer_id, crop, mode in zip_inputs(layer_id_link, crop, mode_link):
            if not isinstance(layer_id, str):
                raise WorkflowError(f"[#{node_id} Krita Layers]\nlayer_id must be a constant string")

            if not isinstance(mode, str):
                raise WorkflowError(f"[#{node_id} Krita Layers]\nmode must be a constant string")

            # If the layer name is empty, throw an error
            if layer_id == "":
                if error is None:
                    # TODO maybe raise the error immediately?
                    if isinstance(layer_id_link, UiLink):
                        error = workflow.graph.error(f"Layer selector [{", ".join(layer_id_link.ids)}] is empty")
                    else:
                        error = workflow.graph.error(f"[#{node_id} Krita Layers]\nlayer_id is empty")

                images.append(error)
                masks.append(error)
                names.append(error)

            else:
                layers = self.get_layers(workflow, layer_id, crop, mode)
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


CONST_NODES = {
    "krita_comfyui: KritaUiBoolean": KritaUi("boolean", ["value", "is_default"]),
    "krita_comfyui: KritaUiCombo": KritaUi("combo", ["value", "label", "is_default"]),
    "krita_comfyui: KritaUiFloat": KritaUi("float", ["value", "is_default"]),
    "krita_comfyui: KritaUiInt": KritaUi("int", ["value", "is_default"]),
    "krita_comfyui: KritaUiLayerId": KritaUi("layer_id", ["value", "layer_name", "is_default"]),
    "krita_comfyui: KritaUiString": KritaUi("string", ["value", "is_default"]),
    "krita_comfyui: KritaUiPrompt": KritaUi("prompt", ["positive", "negative", "is_default"]),

    "krita_comfyui: KritaCanvas": KritaCanvas(),
    "krita_comfyui: KritaLayers": KritaLayers(),
    "krita_comfyui: KritaDebug": KritaDebug(),
    "krita_comfyui: KritaSeed": KritaSeed(),
}

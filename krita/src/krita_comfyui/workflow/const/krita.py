# This module contains constant-evaluation versions of the Krita nodes.
from . import WorkflowError, Link, ConstantNode, ConstantOutputs, InputValue, InputDynamicCombo, function
from ...util.krita import Bounds
from ... import shared


class UiLink(Link):
    def __init__(self, values, ids):
        super().__init__(values)
        self.ids = ids


def krita_ui(type, outputs):
    def get_id(id):
        return f"{type}/{id}"

    class KritaUi(ConstantNode):
        def run(self):
            ids = []
            links = [UiLink([], ids) for _ in outputs]

            for id in self.evaluate_input("id").values:
                id = get_id(id)
                values = self.workflow.get_ui_values(id)

                ids.append(id)

                for link, key in zip(links, outputs):
                    link.values.extend([value[key] for value in values])

            return ConstantOutputs(links)

    return KritaUi


class KritaUiPrompt(krita_ui("prompt", ["positive", "negative", "loras", "is_default"])):
    def run(self):
        outputs = super().run()

        # Flattens the loras into a single flat list
        outputs.links[2].values = [lora for value in outputs.links[2].values for lora in value]

        return outputs


@function(
    name="Krita Canvas: Image",
    inputs_constant=True,
    inputs={
        "crop": InputValue(optional=True),
    },
    outputs=2,
)
class KritaCanvasImage(ConstantNode):
    def run(self, crop):
        if crop is None:
            crop = self.workflow.bounds()
        else:
            crop = Bounds.from_json(crop)

        cached_canvas = self.workflow.cached_canvas.get(crop, None)

        if cached_canvas is None:
            image = self.workflow.document.canvas(crop)
            cached_canvas = self.workflow.graph.image(image)
            self.workflow.cached_canvas[crop] = cached_canvas

        return cached_canvas


@function(
    name="Krita Canvas: Size",
    inputs_constant=True,
    outputs=2,
)
class KritaCanvasSize(ConstantNode):
    def run(self):
        bounds = self.workflow.bounds()
        return (
            bounds.width,
            bounds.height,
        )


class KritaDebug(ConstantNode):
    def run(self):
        enabled = self.evaluate_input("enabled")

        (all_true, all_false) = enabled.check_booleans()

        # If it's disabled, don't evaluate anything.
        if all_false and not all_true:
            return ConstantOutputs([])

        else:
            outputs = {}

            text = self.evaluate_input("text", optional=True)

            if text is None:
                text = Link([])

            # We need to do this so that way it's possible to debug loras from a Krita Ui Prompt.
            text.transform(shared.serialize_any)

            for key, value in self.inputs.items():
                if key == "enabled":
                    outputs[key] = enabled.to_node(self.graph)
                elif key == "text":
                    outputs[key] = text.to_node(self.graph)
                else:
                    outputs[key] = self.workflow.evaluate_link(value).to_node(self.graph)

            self.graph.node(self.node_name, **outputs)

            return ConstantOutputs([])


@function(
    name="Krita Layers",
    inputs_constant=True,
    inputs={
        "layer_id": InputValue(raw_link=True),
        "crop": InputValue(optional=True),
    },
    is_input_list=True,
    is_output_list=True,
    outputs=3,
)
class KritaLayers(ConstantNode):
    def get_layer_image(self, layer, crop):
        image = self.workflow.cached_layer_images.get((layer.id, crop), None)

        if image is None:
            image = self.workflow.graph.image(layer.image(crop))
            self.workflow.cached_layer_images[(layer.id, crop)] = image

        return image


    def get_layers(self, layer_id, crop, mode):
        layers = self.workflow.cached_layers.get((layer_id, crop, mode), None)

        if layers is None:
            images = []
            masks = []
            names = []

            layer = self.workflow.document.find_layer_by_id(layer_id)

            if layer is None:
                self.error(f"Could not find layer {layer_id}")

            def add_image(layer):
                (image, mask) = self.get_layer_image(layer, crop)
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
                self.error("mode must be individual or flatten")

            layers = (images, masks, names)
            self.workflow.cached_layers[(layer_id, crop, mode)] = layers

        return layers


    def run(self, layer_id, crop, mode):
        layer_id_link = layer_id

        images = []
        masks = []
        names = []

        for layer_id, crop, mode in shared.zip_lists([layer_id.values, crop, mode]):
            if crop is None:
                crop = self.workflow.bounds()
            else:
                crop = Bounds.from_json(crop)

            # If the layer name is empty, throw an error
            if layer_id == "":
                if isinstance(layer_id_link, UiLink):
                    raise WorkflowError(f"Layer selector [{", ".join(layer_id_link.ids)}] is empty")
                else:
                    self.error("layer_id is empty")
            else:
                image, mask, name = self.get_layers(layer_id, crop, mode)
                images.extend(image)
                masks.extend(mask)
                names.extend(name)

        return (images, masks, names)


@function(
    name="Krita Seed",
    inputs_constant=True,
)
class KritaSeed(ConstantNode):
    def run(self):
        return self.workflow.seed


# This could be implemented in ComfyUI, except prompt loras are only
# accessible in Krita, so we have to constant evaluate it.
@function(
    name="Apply Loras",
    inputs={
        "loras": InputValue(constant=True, optional=True),
    },
    outputs=2,
    is_input_list=True,
    is_output_list=True,
)
class ApplyLoras(ConstantNode):
    def run(self, model, clip, loras):
        seen_loras = set()

        for lora in loras:
            if lora is not None:
                path = lora["path"]

                if path in seen_loras:
                    self.error(f"Duplicate lora: {path}")

                seen_loras.add(path)

        models = []
        clips = []

        for model, clip in shared.zip_lists([model, clip]):
            for lora in loras:
                if lora is not None:
                    model_weight = lora["model_weight"]
                    clip_weight = lora["clip_weight"]

                    assert model_weight != 0.0 or clip_weight != 0.0

                    load_lora = self.graph.node(
                        "LoraLoader",
                        model=model,
                        clip=clip,
                        lora_name=lora["path"],
                        strength_model=model_weight,
                        strength_clip=clip_weight,
                    )

                    model = load_lora.out(0)
                    clip = load_lora.out(1)

            models.append(model)
            clips.append(clip)

        return (models, clips)


@function(
    name="Detail Size",
    inputs_constant=True,
    inputs={
        "resize_type": InputDynamicCombo(),
    },
    outputs=2,
)
class DetailSize(ConstantNode):
    def run(self, width, height, resize_type, round_up, integer_multiple):
        return shared.detail_size(width, height, resize_type, round_up, integer_multiple)


CONST_NODES = {
    "krita_comfyui: KritaUiBoolean": krita_ui("boolean", ["value", "is_default"]),
    "krita_comfyui: KritaUiCombo": krita_ui("combo", ["value", "label", "is_default"]),
    "krita_comfyui: KritaUiFloat": krita_ui("float", ["value", "is_default"]),
    "krita_comfyui: KritaUiInt": krita_ui("int", ["value", "is_default"]),
    "krita_comfyui: KritaUiLayerId": krita_ui("layer_id", ["value", "layer_name", "is_default"]),
    "krita_comfyui: KritaUiString": krita_ui("string", ["value", "is_default"]),
    "krita_comfyui: KritaUiPrompt": KritaUiPrompt,

    "krita_comfyui: KritaCanvasImage": KritaCanvasImage,
    "krita_comfyui: KritaCanvasSize": KritaCanvasSize,
    "krita_comfyui: KritaLayers": KritaLayers,
    "krita_comfyui: KritaDebug": KritaDebug,
    "krita_comfyui: KritaSeed": KritaSeed,
    "krita_comfyui: ApplyLoras": ApplyLoras,

    "krita_comfyui: DetailSize": DetailSize,
}

# This module contains constant-evaluation versions of the Krita nodes.
from shared import MIN_SEED, MAX_SEED, serialize_any, zip_lists, detail_size
from . import WorkflowError, Link, ConstantNode, ConstantOutputs, InputValue, InputDynamicCombo, is_link, function, constant
from ...util.krita import Bounds


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


@function(
    name="Krita Live Mode",
    inputs_constant=True,
)
class KritaLiveMode(ConstantNode):
    def run(self):
        return self.workflow.is_live_mode


class KritaDebug(ConstantNode):
    def serialize_any(self, x):
        if is_link(x):
            return x
        else:
            return serialize_any(x)


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
            text.transform(self.serialize_any)

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

        for layer_id, crop, mode in zip_lists([layer_id.values, crop, mode]):
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


class KritaSeed(ConstantNode):
    @staticmethod
    def normalize(seed):
        assert seed >= MIN_SEED and seed <= MAX_SEED

        # https://github.com/Comfy-Org/ComfyUI/blob/ed201fff08fbbd3dbcc500b252a9f41e8051c256/nodes.py#L1570
        # https://github.com/Comfy-Org/ComfyUI/blob/ed201fff08fbbd3dbcc500b252a9f41e8051c256/comfy_extras/nodes_primitive.py#L52
        # We have to normalize the integer into the range of [0, sys.maxsize]
        return seed - MIN_SEED

    def run(self):
        seeds = []
        is_fixed = []

        info = self.workflow.get_ui_values("seed/seed")

        if len(info) == 0:
            seeds.append(self.normalize(self.workflow.random_seed()))
            is_fixed.append(False)

        else:
            for info in info:
                if info["fixed"]:
                    seeds.append(self.normalize(info["seed"]))
                    is_fixed.append(True)
                else:
                    seeds.append(self.normalize(self.workflow.random_seed()))
                    is_fixed.append(False)

        return ConstantOutputs([Link(seeds), Link(is_fixed)])


# This could be implemented in ComfyUI, except prompt loras are only
# accessible in Krita, so we have to constant evaluate it.
@function(
    name="Apply Loras",
    inputs_allow_links=True,
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

        for model, clip in zip_lists([model, clip]):
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
    outputs=3,
)
class DetailSize(ConstantNode):
    def run(self, width, height, resize_type, round_up, integer_multiple):
        new_width, new_height = detail_size(width, height, resize_type, round_up, integer_multiple)

        is_changed = (new_width != width) or (new_height != height)

        return (new_width, new_height, is_changed)


@function(
    name="Make Control Net",
    inputs={
        "image": InputValue(allow_links=True),
        "mask": InputValue(allow_links=True, optional=True),
        "model": InputValue(allow_links=True),
        "type": InputDynamicCombo(),
        "strength": InputValue(),
        "start_percent": InputValue(),
        "end_percent": InputValue(),
    },
)
class MakeControlNet(ConstantNode):
    def run(self, image, mask, model, type, strength, start_percent, end_percent):
        return {
            "image": image,
            "mask": mask,
            "model": model,
            "type": type,
            "strength": strength,
            "start_percent": start_percent,
            "end_percent": end_percent,
        }


@function(
    name="Apply Control Nets",
    inputs={
        "model": InputValue(allow_links=True),
        "positive": InputValue(allow_links=True),
        "negative": InputValue(allow_links=True),
        "vae": InputValue(allow_links=True),
        "control_nets": InputValue(optional=True),
    },
    outputs=4,
    is_input_list=True,
    is_output_list=True,
)
class ApplyControlNets(ConstantNode):
    def anima(self, model, control_net, image):
        return self.graph.node("AnimaLLLiteApply",
            model=model,
            lllite_name=control_net["model"],
            image=image,
            mask=control_net["mask"],
            strength=control_net["strength"],
            start_percent=control_net["start_percent"],
            end_percent=control_net["end_percent"],
        ).out(0)


    def union(self, positive, negative, vae, control_net, image):
        model = self.graph.node("ControlNetLoader", control_net_name=control_net["model"]).out(0)
        model = self.graph.node("SetUnionControlNetType", control_net=model, type=control_net["type"]["union_type"]).out(0)

        apply = self.graph.node("ControlNetApplyAdvanced",
            positive=positive,
            negative=negative,
            control_net=model,
            image=image,
            vae=vae,
            strength=control_net["strength"],
            start_percent=control_net["start_percent"],
            end_percent=control_net["end_percent"],
        )

        positive = apply.out(0)
        negative = apply.out(1)
        return (positive, negative)


    def run(self, model, positive, negative, vae, control_nets):
        models = []
        positives = []
        negatives = []
        images = []

        for model, positive, negative, vae in zip_lists([model, positive, negative, vae]):
            for control_net in control_nets:
                if (
                    control_net is not None and
                    control_net["strength"] > 0.0 and
                    control_net["start_percent"] < control_net["end_percent"]
                ):
                    image = control_net["image"]
                    images.append(image)

                    match control_net["type"]["type"]:
                        case "Anima LLLite":
                            model = self.anima(model, control_net, image)

                        case "Union":
                            (positive, negative) = self.union(positive, negative, vae, control_net, image)

                        case x:
                            self.error(f"Unknown type {x}")

            models.append(model)
            positives.append(positive)
            negatives.append(negative)

        return (models, positives, negatives, images)


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
    "krita_comfyui: KritaLiveMode": KritaLiveMode,
    "krita_comfyui: KritaDebug": KritaDebug,
    "krita_comfyui: KritaSeed": KritaSeed,
    "krita_comfyui: ApplyLoras": ApplyLoras,

    "krita_comfyui: EmptyControlNet": constant(None),
    "krita_comfyui: MakeControlNet": MakeControlNet,
    "krita_comfyui: ApplyControlNets": ApplyControlNets,

    "krita_comfyui: DetailSize": DetailSize,
}

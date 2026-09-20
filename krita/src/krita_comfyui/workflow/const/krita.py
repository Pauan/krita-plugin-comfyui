# This module contains constant-evaluation versions of the Krita nodes.
from typing import Any
from collections.abc import Sequence
from shared.graph import NodeLink
from shared import MIN_SEED, MAX_SEED, serialize_any, zip_lists, detail_size
from . import WorkflowError, Link, ConstantNode, ConstantOutputs, InputValue, InputDynamicCombo, is_link, function, constant
from ...util.krita import ROOT_LAYER_ID, Bounds, Layer


class UiLink(Link):
    def __init__(self, values: list[Any], ids: list[str]) -> None:
        super().__init__(values)
        self.ids = ids


def krita_ui(type: str, outputs: Sequence[str]) -> type[ConstantNode]:
    def get_id(id: str) -> str:
        return f"{type}/{id}"

    class KritaUi(ConstantNode):
        def run(self) -> ConstantOutputs:
            ids: list[str] = []
            links: list[Link] = [UiLink([], ids) for _ in outputs]

            for id in self.evaluate_input("id").values:
                id = get_id(id)
                values = self.workflow.get_ui_values(id)

                ids.append(id)

                for link, key in zip(links, outputs):
                    link.values.extend([value[key] for value in values])

            return ConstantOutputs(links)

    return KritaUi


class KritaUiPrompt(krita_ui("prompt", ["positive", "negative", "loras", "is_default"])):
    def run(self) -> ConstantOutputs:
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
    def run(self, crop: Any) -> Any:
        if crop is None:
            bounds = self.workflow.bounds()
        else:
            bounds = Bounds.from_json(crop)

        return self.workflow.get_cached_canvas(bounds)


@function(
    name="Krita Canvas: Size",
    inputs_constant=True,
    outputs=2,
)
class KritaCanvasSize(ConstantNode):
    def run(self) -> tuple[int, int]:
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
    def run(self) -> bool:
        return self.workflow.is_live_mode


class KritaDebug(ConstantNode):
    def serialize_any(self, x: Any) -> Any:
        if is_link(x):
            return x
        else:
            return serialize_any(x)


    def run(self) -> ConstantOutputs:
        enabled = self.evaluate_input("enabled")

        (all_true, all_false) = enabled.check_booleans()

        # If it's disabled, don't evaluate anything.
        if all_false and not all_true:
            return ConstantOutputs([])

        else:
            outputs: dict[str, Any] = {}

            text = self.evaluate_input("text", optional=True)

            if text is None:
                text = Link([])
            else:
                # We need to do this so that way it's possible to debug loras from a Krita Ui Prompt.
                text = text.map(self.serialize_any)

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
    def get_layer_image(self, layer: Layer, crop: Bounds) -> tuple[Any, Any]:
        image = self.workflow.cached_layer_images.get((layer.id, crop), None)

        if image is None:
            image = layer.image(crop)
            image = (
                image.rgb_view(),
                image.alpha_view(),
            )
            self.workflow.cached_layer_images[(layer.id, crop)] = image

        return image


    def get_layers(self, layer_id: str, crop: Bounds, mode: str) -> tuple[list[Any], list[Any], list[str]]:
        layers = self.workflow.cached_layers.get((layer_id, crop, mode), None)

        if layers is None:
            images: list[Any] = []
            masks: list[Any] = []
            names: list[str] = []

            root_layer = self.workflow.document.root_layer()

            if layer_id == ROOT_LAYER_ID:
                layer = root_layer
            else:
                layer = self.workflow.document.find_layer_by_id(layer_id)

            assert root_layer is not None

            if layer is None:
                self.error(f"Could not find layer {layer_id}")

            def add_image(layer: Layer) -> None:
                if layer.id == root_layer.id:
                    (image, mask) = self.workflow.get_cached_canvas(crop)
                else:
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


    def run(self, layer_id: Link, crop: list[Any], mode: list[str]) -> tuple[list[Any], list[Any], list[str]]:
        layer_id_link = layer_id

        images: list[Any] = []
        masks: list[Any] = []
        names: list[str] = []

        for id, crop_json, layer_mode in zip_lists([layer_id.values, crop, mode]):
            if crop_json is None:
                bounds = self.workflow.bounds()
            else:
                bounds = Bounds.from_json(crop_json)

            # If the layer name is empty, throw an error
            if id == "":
                if isinstance(layer_id_link, UiLink):
                    raise WorkflowError(f"Layer selector [{", ".join(layer_id_link.ids)}] is empty")
                else:
                    self.error("layer_id is empty")
            else:
                image, mask, name = self.get_layers(id, bounds, layer_mode)
                images.extend(image)
                masks.extend(mask)
                names.extend(name)

        return (images, masks, names)


@function()
class KritaAnimationFrames(ConstantNode):
    def run(self) -> int:
        return self.workflow.document.get_animation_length()


class KritaSeed(ConstantNode):
    @staticmethod
    def normalize(seed: int) -> int:
        assert seed >= MIN_SEED and seed <= MAX_SEED

        # https://github.com/Comfy-Org/ComfyUI/blob/ed201fff08fbbd3dbcc500b252a9f41e8051c256/nodes.py#L1570
        # https://github.com/Comfy-Org/ComfyUI/blob/ed201fff08fbbd3dbcc500b252a9f41e8051c256/comfy_extras/nodes_primitive.py#L52
        # We have to normalize the integer into the range of [0, sys.maxsize]
        return seed - MIN_SEED

    def run(self) -> ConstantOutputs:
        seeds: list[int] = []
        is_fixed: list[bool] = []

        fixed = self.workflow.get_ui_values("seed/fixed")
        seed = self.workflow.get_ui_values("seed/seed")

        assert len(fixed) == len(seed)

        for fixed, seed in zip(fixed, seed):
            if fixed["value"]:
                seeds.append(self.normalize(seed["value"]))
                is_fixed.append(True)
            else:
                seeds.append(self.normalize(self.workflow.random_seed()))
                is_fixed.append(False)

        if len(seeds) == 0:
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
    def run(self, model: list[Any], clip: list[Any], loras: list[dict[str, Any] | None]) -> tuple[list[Any], list[Any]]:
        seen_loras: set[str] = set()

        for lora in loras:
            if lora is not None:
                path = lora["path"]

                if path in seen_loras:
                    self.error(f"Duplicate lora: {path}")

                seen_loras.add(path)

        models: list[Any] = []
        clips: list[Any] = []

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
    def run(self, width: int, height: int, resize_type: Any, round_up: int, integer_multiple: bool) -> tuple[int, int, bool]:
        new_width, new_height = detail_size(width, height, resize_type, round_up, integer_multiple)

        is_changed = (new_width != width) or (new_height != height)

        return (new_width, new_height, is_changed)


@function(
    name="Make Control Net",
    inputs={
        "image": InputValue(allow_links=True),
        "mask": InputValue(allow_links=True, optional=True),
        "model": InputValue(allow_links=True),
        "type": InputValue(),
        "strength": InputValue(),
        "start_percent": InputValue(),
        "end_percent": InputValue(),
    },
)
class MakeControlNet(ConstantNode):
    def run(self, image: Any, mask: Any, model: Any, type: str, strength: float, start_percent: float, end_percent: float) -> dict[str, Any]:
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
    def anima(self, model: NodeLink, control_net: dict[str, Any], image: NodeLink) -> NodeLink:
        return self.graph.node("AnimaLLLiteApply",
            model=model,
            lllite_name=control_net["model"],
            image=image,
            mask=control_net["mask"],
            strength=control_net["strength"],
            start_percent=control_net["start_percent"],
            end_percent=control_net["end_percent"],
        ).out(0)


    def union(self, positive: NodeLink, negative: NodeLink, vae: NodeLink, control_net: dict[str, Any], image: NodeLink) -> tuple[NodeLink, NodeLink]:
        model = self.graph.node("ControlNetLoader", control_net_name=control_net["model"]).out(0)
        model = self.graph.node("SetUnionControlNetType", control_net=model, type=control_net["type"]).out(0)

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


    def z_image(self, model: NodeLink, vae: NodeLink, control_net: dict[str, Any], image: NodeLink) -> NodeLink:
        model_patch = self.graph.node("ModelPatchLoader",
            name=control_net["model"],
        ).out(0)

        return self.graph.node("ZImageFunControlnet",
            model=model,
            model_patch=model_patch,
            vae=vae,
            strength=control_net["strength"],
            image=image,
            mask=control_net["mask"],
        ).out(0)


    def run(self, model: list[Any], positive: list[Any], negative: list[Any], vae: list[Any], control_nets: list[dict[str, Any] | None]) -> tuple[list[Any], list[Any], list[Any], list[Any]]:
        models: list[Any] = []
        positives: list[Any] = []
        negatives: list[Any] = []
        images: list[Any] = []

        for model, positive, negative, vae in zip_lists([model, positive, negative, vae]):
            for control_net in control_nets:
                if (
                    control_net is not None and
                    control_net["strength"] > 0.0 and
                    control_net["start_percent"] < control_net["end_percent"]
                ):
                    image = control_net["image"]
                    images.append(image)

                    match control_net["type"]:
                        case "Anima":
                            model = self.anima(model, control_net, image)

                        case "Z-Image":
                            model = self.z_image(model, vae, control_net, image)

                        case _:
                            (positive, negative) = self.union(positive, negative, vae, control_net, image)

            models.append(model)
            positives.append(positive)
            negatives.append(negative)

        return (models, positives, negatives, images)


# This is just so we can remove any unused regions.
@function(
    name="Region Mask",
    inputs={
        "mask": InputValue(constant=True, optional=True),
        "name": InputValue(constant=True, optional=True),
    },
    outputs=1,
    is_input_list=True,
    is_output_list=True,
)
class RegionMask(ConstantNode):
    def run(self, mask: list[Any], name: list[Any], prompt: list[Any], strength: list[Any], isolated: list[Any], add_to_global: list[Any]) -> list[Any]:
        outputs: list[Any] = []

        for mask_, name_, prompt_, strength_, isolated_, add_to_global_ in zip_lists([mask, name, prompt, strength, isolated, add_to_global]):
            if strength_ > 0.0 and mask_ is not None:
                prompt_ = prompt_.strip()

                if prompt_ != "" and (not mask_.is_solid(0x00)):
                    outputs.append(self.graph.node("krita_comfyui: RegionMask",
                        mask=mask_,
                        name=name_,
                        prompt=prompt_,
                        strength=strength_,
                        isolated=isolated_,
                        add_to_global=add_to_global_,
                    ).out(0))

        return outputs


CONST_NODES = {
    "krita_comfyui: KritaUiBoolean": krita_ui("boolean", ["value", "is_default"]),
    "krita_comfyui: KritaUiCombo": krita_ui("combo", ["value", "label", "is_default"]),
    "krita_comfyui: KritaUiFloat": krita_ui("float", ["value", "is_default"]),
    "krita_comfyui: KritaUiInt": krita_ui("int", ["value", "is_default"]),
    "krita_comfyui: KritaUiLayerId": krita_ui("layer_id", ["value", "layer_name", "is_default"]),
    "krita_comfyui: KritaUiString": krita_ui("string", ["value", "is_default"]),
    "krita_comfyui: KritaUiPrompt": KritaUiPrompt,

    "krita_comfyui: KritaAnimationFrames": KritaAnimationFrames,
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

    "krita_comfyui: RegionMask": RegionMask,
}

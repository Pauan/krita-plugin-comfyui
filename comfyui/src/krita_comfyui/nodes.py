import math
from comfy_api.latest import io
from comfy_execution.graph_utils import GraphBuilder
from .util import timestamp, decode_image, decode_mask, encode_image, serialize_any, zip_lists, graph_list, is_image, get_size


def always_execute():
    # Hack that causes ComfyUI to always execute the node
    # https://github.com/Comfy-Org/ComfyUI/discussions/12546
    return float("nan")


# @TODO Move this functionality into the ComfyUI CreateList node
class MakeList(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        template_matchtype = io.MatchType.Template("type")
        template_autogrow = io.Autogrow.TemplatePrefix(
            input=io.MatchType.Input("input", template=template_matchtype, optional=True),
            prefix="input",
        )
        return io.Schema(
            node_id="krita_comfyui: MakeList",
            display_name="Make List",
            category="logic",
            description="Makes a list",
            inputs=[
                io.Autogrow.Input("inputs", template=template_autogrow, optional=True),
            ],
            outputs=[
                io.MatchType.Output(
                    template=template_matchtype,
                    is_output_list=True,
                    display_name="list",
                ),
            ],
            is_input_list=True,
        )

    @classmethod
    def execute(cls, inputs={}) -> io.NodeOutput:
        output_list = []
        for input in inputs.values():
            output_list += input
        return io.NodeOutput(output_list)


# TODO move this into ComfyUI
class Default(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        template = io.MatchType.Template("type")
        return io.Schema(
            node_id="krita_comfyui: Default",
            display_name="Default",
            category="logic",
            description="Sets a default value if the input is empty.",
            inputs=[
                io.MatchType.Input("input", template=template),
                io.MatchType.Input("default", template=template, lazy=True),
            ],
            outputs=[
                io.MatchType.Output(
                    template=template,
                    is_output_list=True,
                    display_name="output",
                ),
            ],
            is_input_list=True,
        )

    @classmethod
    def check_lazy_status(cls, input, default):
        needed = []
        if len(input) == 0:
            if default is None or (len(default) == 1 and default[0] is None):
                needed.append("default")
        return needed

    @classmethod
    def execute(cls, input, default=[]) -> io.NodeOutput:
        if len(input) == 0:
            return io.NodeOutput(default)
        else:
            return io.NodeOutput(input)


# TODO move this into ComfyUI
class ReplaceTransparency(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: ReplaceTransparency",
            display_name="Image Replace Transparency",
            category="image",
            description="Replaces the alpha transparency of an image with a color.",
            inputs=[
                io.Image.Input("image"),
                io.Color.Input("color", default="#ffffff", tooltip="The transparency will be replaced with this color."),
            ],
            outputs=[
                io.Image.Output(display_name="image"),
            ],
            enable_expand=True,
        )

    @classmethod
    def execute(cls, image, color) -> io.NodeOutput:
        # TODO this should be moved into the Color type
        assert color[0] == "#"
        color = int("0x" + color[1:], 16)

        graph = GraphBuilder()

        size = graph.node("GetImageSize", image=image)

        empty_image = graph.node("EmptyImage",
            width=size.out(0),
            height=size.out(1),
            batch_size=size.out(2),
            color=color,
        ).out(0)

        split_image = graph.node("SplitImageWithAlpha", image=image)

        mask = graph.node("InvertMask", mask=split_image.out(1)).out(0)

        image = graph.node("ImageCompositeMasked",
            destination=empty_image,
            source=split_image.out(0),
            mask=mask,
            x=0,
            y=0,
            resize_source=False,
        ).out(0)

        return io.NodeOutput(image, expand=graph.finalize())


@io.comfytype(io_type="KRITA_LAYER_ID")
class LayerId(io.ComfyTypeIO):
    Type = str


@io.comfytype(io_type="KRITA_SELECTION")
class Selection(io.ComfyTypeIO):
    pass


class LoadImageBase64(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: LoadImageBase64",
            display_name="Load Image (Base64)",
            category="image",
            description="Converts a base64 string into an image.",
            inputs=[
                io.String.Input("base64", tooltip="RGBA bytes formatted as base64."),
                io.Int.Input("width", tooltip="Number of horizontal pixels."),
                io.Int.Input("height", tooltip="Number of vertical pixels."),
            ],
            outputs=[
                io.Image.Output(display_name="image"),
                io.Mask.Output(display_name="mask"),
            ],
        )

    @classmethod
    def execute(cls, base64, width, height) -> io.NodeOutput:
        (image, mask) = decode_image(base64, width, height)
        return io.NodeOutput(image, mask)


class LoadMaskBase64(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: LoadMaskBase64",
            display_name="Load Mask (Base64)",
            category="image",
            description="Converts a base64 string into a mask.",
            inputs=[
                io.String.Input("base64", tooltip="Grayscale bytes formatted as base64"),
                io.Int.Input("width", tooltip="Number of horizontal pixels."),
                io.Int.Input("height", tooltip="Number of vertical pixels."),
            ],
            outputs=[
                io.Mask.Output(display_name="mask"),
            ],
        )

    @classmethod
    def execute(cls, base64, width, height) -> io.NodeOutput:
        return io.NodeOutput(decode_mask(base64, width, height))


class ThrowError(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: ThrowError",
            display_name="Throw Error",
            description="Throws an error when evaluated.",
            inputs=[
                io.String.Input("message"),
            ],
            outputs=[
                io.AnyType.Output(display_name="any"),
            ],
        )

    @classmethod
    def execute(cls, message) -> io.NodeOutput:
        raise RuntimeError(message)


class KritaLayers(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaLayers",
            display_name="Krita Layers",
            category="krita",
            description="Retrieves one or more layers from Krita.",
            inputs=[
                LayerId.Input("layer_id", tooltip="The unique ID of the layer."),
                io.Combo.Input("mode", options=["individual", "flatten"], default="individual", tooltip="How to process the layers.\n\n* individual: Return each layer as an individual image.\n* flatten: Flatten the layers into one image."),
            ],
            outputs=[
                io.Image.Output(display_name="images", is_output_list=True),
                io.Mask.Output(display_name="masks", is_output_list=True),
                io.String.Output(display_name="names", is_output_list=True),
            ],
        )

    @classmethod
    def execute(cls, layer_id, mode) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaCanvas(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaCanvas",
            display_name="Krita Canvas",
            category="krita",
            description="Retrieves the entire canvas from Krita.",
            inputs=[],
            outputs=[
                io.Image.Output(display_name="image"),
                io.Mask.Output(display_name="mask"),
                io.Int.Output(display_name="width"),
                io.Int.Output(display_name="height"),
            ],
        )

    @classmethod
    def execute(cls) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaSeed(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaSeed",
            display_name="Krita Seed",
            category="krita",
            description="Retrieves the seed from Krita.",
            inputs=[],
            outputs=[
                io.Int.Output(display_name="seed"),
            ],
        )

    @classmethod
    def execute(cls) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaSelection(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaSelection",
            display_name="Krita Selection",
            category="krita/selection",
            description="Retrieves the selection from Krita.",
            inputs=[],
            outputs=[
                Selection.Output(display_name="selection"),
                io.Boolean.Output(display_name="is_active", tooltip="Whether the selection exists in Krita or not."),
            ],
        )

    @classmethod
    def execute(cls) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaSelectionGrow(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaSelectionGrow",
            display_name="Krita Selection: Grow",
            category="krita/selection",
            description="Grows the Krita selection.",
            inputs=[
                Selection.Input("selection"),
                io.Int.Input("x", tooltip="X width for growing the selection."),
                io.Int.Input("y", tooltip="Y height for growing the selection."),
            ],
            outputs=[
                Selection.Output(display_name="selection"),
            ],
        )

    @classmethod
    def execute(cls, selection, x, y) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaSelectionShrink(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaSelectionShrink",
            display_name="Krita Selection: Shrink",
            category="krita/selection",
            description="Shrinks the Krita selection.",
            inputs=[
                Selection.Input("selection"),
                io.Int.Input("x", tooltip="X width for shrinking the selection."),
                io.Int.Input("y", tooltip="Y height for shrinking the selection."),
            ],
            outputs=[
                Selection.Output(display_name="selection"),
            ],
        )

    @classmethod
    def execute(cls, selection, x, y) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaSelectionFeather(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaSelectionFeather",
            display_name="Krita Selection: Feather",
            category="krita/selection",
            description="Feathers the Krita selection.",
            inputs=[
                Selection.Input("selection"),
                io.Int.Input("amount", tooltip="Radius for feathering the selection."),
                io.Combo.Input("mode", options=["outside", "inside", "both"], default="outside", tooltip="Whether to feather outside or inside the selection."),
            ],
            outputs=[
                Selection.Output(display_name="selection"),
            ],
        )

    @classmethod
    def execute(cls, selection, amount, mode) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaSelectionBorder(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaSelectionBorder",
            display_name="Krita Selection: Border",
            category="krita/selection",
            description="Adds a border around the Krita selection.",
            inputs=[
                Selection.Input("selection"),
                io.Int.Input("x", tooltip="X width of the border."),
                io.Int.Input("y", tooltip="Y height of the border."),
                io.Combo.Input("mode", options=["outside", "inside", "both"], default="outside", tooltip="Whether to border outside or inside the selection."),
            ],
            outputs=[
                Selection.Output(display_name="selection"),
            ],
        )

    @classmethod
    def execute(cls, selection, x, y, mode) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaSelectionSmooth(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaSelectionSmooth",
            display_name="Krita Selection: Smooth",
            category="krita/selection",
            description="Smooths the Krita selection.",
            inputs=[
                Selection.Input("selection"),
            ],
            outputs=[
                Selection.Output(display_name="selection"),
            ],
        )

    @classmethod
    def execute(cls, selection) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaSelectionInvert(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaSelectionInvert",
            display_name="Krita Selection: Invert",
            category="krita/selection",
            description="Inverts the Krita selection.",
            inputs=[
                Selection.Input("selection"),
            ],
            outputs=[
                Selection.Output(display_name="selection"),
            ],
        )

    @classmethod
    def execute(cls, selection) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaSelectionBounds(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaSelectionBounds",
            display_name="Krita Selection: Bounds",
            category="krita/selection",
            description="Retrieves the bounds of the Krita selection.",
            inputs=[
                Selection.Input("selection"),
                io.Int.Input("round_up", min=1, default=32, tooltip="Rounds up to the nearest multiple. Set to 1 to disable rounding."),
            ],
            outputs=[
                io.Int.Output(display_name="x"),
                io.Int.Output(display_name="y"),
                io.Int.Output(display_name="width"),
                io.Int.Output(display_name="height"),
            ],
        )

    @classmethod
    def execute(cls, selection) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaSelectionMask(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaSelectionMask",
            display_name="Krita Selection: Mask",
            category="krita/selection",
            description="Retrieves the mask of the Krita selection.",
            inputs=[
                Selection.Input("selection"),
            ],
            outputs=[
                io.Mask.Output(display_name="mask"),
            ],
        )

    @classmethod
    def execute(cls, selection) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaOutput(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaOutput",
            display_name="Krita Output",
            category="krita",
            description="Sends images to Krita.",
            inputs=[
                io.Image.Input("images", tooltip="Images that will be sent to Krita."),
                io.Int.Input("x", default=0, tooltip="X position relative to the canvas."),
                io.Int.Input("y", default=0, tooltip="Y position relative to the canvas."),

                io.String.Input("name",
                    default="ComfyUI [%index%]",
                    tooltip="""Name that will be used for the images in Krita.

You can use the following special syntax:

  %index% is replaced with the index of the image.

  %timestamp% is replaced with the current time."""),
            ],
            outputs=[],
            is_input_list=True,
            is_output_node=True,
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return always_execute()

    @classmethod
    def execute(cls, images, x, y, name) -> io.NodeOutput:
        def lookup(list, index):
            return list[min(index, len(list) - 1)]

        def replace_name(name, index):
            time = timestamp()
            return name.replace("%index%", str(index)).replace("%timestamp%", time)

        outputs = []

        list_index = 0
        image_index = 0

        for image in images:
            sub_x = lookup(x, list_index)
            sub_y = lookup(y, list_index)
            sub_name = lookup(name, list_index)

            # https://github.com/Comfy-Org/ComfyUI/blob/ed201fff08fbbd3dbcc500b252a9f41e8051c256/comfy_extras/nodes_images.py#L576-L577
            height = image.shape[1]
            width = image.shape[2]

            for batch in image:
                outputs.append({
                    "bytes": encode_image(batch),
                    "width": width,
                    "height": height,
                    "x": sub_x,
                    "y": sub_y,
                    "name": replace_name(sub_name, image_index),
                })

                image_index += 1

            list_index += 1

        return io.NodeOutput(ui={"krita_comfyui_output_images": outputs})


class KritaText(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaText",
            display_name="Krita Text",
            category="krita",
            description="Sends text to Krita.",
            inputs=[
                io.AnyType.Input("text", tooltip="Will be converted into a string and sent to Krita."),
                io.String.Input("name", default="", tooltip="Name that will be used for the text."),
            ],
            outputs=[],
            is_output_node=True,
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return always_execute()

    @classmethod
    def execute(cls, text, name) -> io.NodeOutput:
        return io.NodeOutput(ui={"krita_comfyui_text": [{ "name": name, "text": serialize_any(text) }]})


class KritaDebug(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaDebug",
            display_name="Krita Debug",
            category="krita/debug",
            description="Sends information to Krita for debugging.",
            inputs=[
                io.Image.Input("images", tooltip="Images that will be debugged.", lazy=True, optional=True),
                io.Mask.Input("masks", tooltip="Masks that will be debugged.", lazy=True, optional=True),
                io.AnyType.Input("text", tooltip="Will be converted into a string and sent to Krita.", lazy=True, optional=True),

                io.Boolean.Input("enabled", default=False, tooltip="Whether to send debug data or not."),
                io.Int.Input("x", default=0, tooltip="X position relative to the canvas.", lazy=True),
                io.Int.Input("y", default=0, tooltip="Y position relative to the canvas.", lazy=True),
                io.String.Input("name", default="", tooltip="Name that is used for the debug.", lazy=True),
            ],
            outputs=[],
            is_input_list=True,
            is_output_node=True,
            enable_expand=True,
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return always_execute()

    @classmethod
    def check_lazy_status(cls, enabled, images=None, masks=None, text=None, x=None, y=None, name=None):
        needed = []

        def check_none(list):
            try:
                return any(x is None for x in list)
            except TypeError:
                return False

        if any(enabled):
            if images is not None and check_none(images):
                needed.append("images")
            if masks is not None and check_none(masks):
                needed.append("masks")
            if text is not None and check_none(text):
                needed.append("text")
            # TODO verify that check_none is needed
            if x is None or check_none(x):
                needed.append("x")
            if y is None or check_none(y):
                needed.append("y")
            if name is None or check_none(name):
                needed.append("name")

        return needed

    @classmethod
    def execute(cls, enabled, x, y, name, images=[], masks=[], text=[]) -> io.NodeOutput:
        graph = GraphBuilder()

        outputs = {}

        for enabled, x, y, name, image, mask, text in zip_lists(enabled, x, y, name, images, masks, text):
            if enabled:
                output = outputs.get(name, None)

                if output is None:
                    output = {
                        "images": [],
                        "masks": [],
                        "texts": [],
                    }

                    outputs[name] = output

                if image is not None:
                    output["images"].append({
                        "image": image,
                        "x": x,
                        "y": y,
                    })

                if mask is not None:
                    output["masks"].append({
                        "mask": mask,
                        "x": x,
                        "y": y,
                    })

                if text is not None:
                    output["texts"].append(text)


        for name, output in outputs.items():
            images = output["images"]

            if len(images) > 0:
                graph.node("krita_comfyui: KritaOutput",
                    images=graph_list(graph, [image["image"] for image in images]),
                    x=graph_list(graph, [image["x"] for image in images]),
                    y=graph_list(graph, [image["y"] for image in images]),
                    name=f"[DEBUG IMAGE] {name} [%index%]"
                )

            masks = output["masks"]

            if len(masks) > 0:
                images = graph.node("MaskToImage", mask=graph_list(graph, [mask["mask"] for mask in masks])).out(0)

                graph.node("krita_comfyui: KritaOutput",
                    images=images,
                    x=graph_list(graph, [mask["x"] for mask in masks]),
                    y=graph_list(graph, [mask["y"] for mask in masks]),
                    name=f"[DEBUG MASK] {name} [%index%]"
                )

            texts = output["texts"]

            if len(texts) > 0:
                graph.node("krita_comfyui: KritaText", text="\n".join(serialize_any(x) for x in texts), name=f"[DEBUG] {name}")

        return io.NodeOutput(None, expand=graph.finalize())


class Img2img(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: img2img",
            display_name="img2img",
            category="latent",
            description="Converts an image into latent space.\n\nIf a mask is provided, then it is used for inpainting.\n\nIf the strength is 0, then it ignores the image and does a regular txt2img.",
            inputs=[
                io.Conditioning.Input("positive"),
                io.Conditioning.Input("negative"),
                io.Vae.Input("vae"),
                io.Image.Input("image"),
                io.Mask.Input("mask", optional=True, tooltip="Optional mask for inpainting."),
                io.Float.Input("strength",
                    default=0.0,
                    min=0.0,
                    max=1.0,
                    step=0.1,
                    round=0.01,
                    tooltip="How much the image should influence the result.\n\nHigher number means it closely matches the image, lower number means more random.\n\n0 means that it ignores the image and does a regular txt2img.",
                ),
                io.Int.Input("batch_size", default=1, min=1, max=64, tooltip="The number of output images in the batch."),
            ],
            outputs=[
                io.Conditioning.Output(display_name="positive"),
                io.Conditioning.Output(display_name="negative"),
                io.Latent.Output(display_name="latent"),
                io.Float.Output(display_name="denoise"),
            ],
            enable_expand=True,
        )

    @classmethod
    def execute(cls, positive, negative, vae, image, strength, batch_size, mask=None) -> io.NodeOutput:
        graph = GraphBuilder()

        if strength == 0.0:
            size = graph.node("GetImageSize", image=image)

            latent = graph.node(
                "EmptyLatentImage",
                width=size.out(0),
                height=size.out(1),
                batch_size=batch_size,
            ).out(0)

        else:
            if mask is None:
                latent = graph.node("VAEEncode", pixels=image, vae=vae).out(0)

            else:
                # VAEEncodeForInpaint doesn't support denoise, so we use InpaintModelConditioning instead
                inpaint_model_conditioning = graph.node(
                    "InpaintModelConditioning",
                    positive=positive,
                    negative=negative,
                    vae=vae,
                    pixels=image,
                    mask=mask,
                    noise_mask=True,
                )

                positive = inpaint_model_conditioning.out(0)
                negative = inpaint_model_conditioning.out(1)
                latent = inpaint_model_conditioning.out(2)

            if batch_size > 1:
                latent = graph.node("RepeatLatentBatch", samples=latent, amount=batch_size).out(0)

        return io.NodeOutput(positive, negative, latent, 1.0 - strength, expand=graph.finalize())


class ClipSkip(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: ClipSkip",
            display_name="CLIP Skip",
            category="conditioning",
            description="Sets the clip skip.",
            inputs=[
                io.Clip.Input("clip"),
                io.Int.Input("skip", default=0, min=0, max=24, step=1, tooltip="0 disables the clip skip."),
            ],
            outputs=[
                io.Clip.Output(),
            ],
            enable_expand=True,
        )

    @classmethod
    def execute(cls, clip, skip) -> io.NodeOutput:
        graph = GraphBuilder()

        if skip > 0:
            clip = graph.node(
                "CLIPSetLastLayer",
                clip=clip,
                stop_at_clip_layer=-skip,
            ).out(0)

        return io.NodeOutput(clip, expand=graph.finalize())


class Detail(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        template = io.MatchType.Template("input_type", [io.Image, io.Mask])

        return io.Schema(
            node_id="krita_comfyui: Detail",
            display_name="Detail",
            category="transform",
            description="Crops and resizes the image / mask.",
            inputs=[
                io.MatchType.Input("input", template=template),

                io.BoundingBox.Input("bounding_box", component=None, tooltip="Crops the image / mask to the bounding box."),

                io.DynamicCombo.Input(
                    "resize_type",
                    tooltip="Select how to resize: by exact dimensions, scale factor, matching another image, etc.",
                    options=[
                        io.DynamicCombo.Option("scale total pixels", [
                            io.Float.Input("megapixels", default=2.0, min=0.0, max=16.0, step=0.01, tooltip="Target total megapixels (e.g., 1.0 ≈ 1024×1024). Aspect ratio is preserved."),
                        ]),
                    ],
                ),

                io.Combo.Input(
                    "scale_method",
                    options=["nearest-exact", "bilinear", "area", "bicubic", "lanczos"],
                    default="lanczos",
                    tooltip="Interpolation algorithm. 'area' is best for downscaling, 'lanczos' for upscaling, 'nearest-exact' for pixel art.",
                ),
            ],
            outputs=[
                io.MatchType.Output(template=template, display_name="cropped"),
                io.MatchType.Output(template=template, display_name="resized"),
            ],
            enable_expand=True,
        )


    @staticmethod
    def should_crop(input, bounding_box):
        if bounding_box["x"] == 0 and bounding_box["y"] == 0:
            (width, height, _) = get_size(input)

            return bounding_box["width"] != width or bounding_box["height"] != height

        else:
            return True


    @staticmethod
    def scale(resize_type, width, height):
        type = resize_type["resize_type"]

        # https://github.com/Comfy-Org/ComfyUI/blob/7d437687c260df7772c603658111148e0e863e59/comfy_extras/nodes_post_processing.py#L281-L289
        if type == "scale by multiplier":
            multiplier = resize_type["multiplier"]

            if multiplier > 1.0:
                width = int(round(width * multiplier))
                height = int(round(height * multiplier))

        # https://github.com/Comfy-Org/ComfyUI/blob/7d437687c260df7772c603658111148e0e863e59/comfy_extras/nodes_post_processing.py#L346-L357
        elif type == "scale total pixels":
            old = float(width * height)
            new = resize_type["megapixels"] * 1024.0 * 1024.0

            if new > old:
                scale_by = math.sqrt(new / old)
                width = int(round(width * scale_by))
                height = int(round(height * scale_by))

        # https://github.com/Comfy-Org/ComfyUI/blob/7d437687c260df7772c603658111148e0e863e59/comfy_extras/nodes_post_processing.py#L306-L324
        # TODO it should leave the width / height unchanged if they are smaller
        elif type == "scale longer dimension":
            largest_size = resize_type["longer_size"]

            if height > width:
                width = int(round((width / height) * largest_size))
                height = largest_size
            elif width > height:
                height = int(round((height / width) * largest_size))
                width = largest_size
            else:
                height = largest_size
                width = largest_size

        else:
            raise RuntimeError(f"Unknown resize_type {type}")

        return (width, height)


    @classmethod
    def execute(cls, input, bounding_box, resize_type, scale_method) -> io.NodeOutput:
        graph = GraphBuilder()

        is_input_image = is_image(input)

        cropped_width = bounding_box["width"]
        cropped_height = bounding_box["height"]

        if cls.should_crop(input, bounding_box):
            if is_input_image:
                cropped = graph.node("ImageCropV2", image=input, crop_region=bounding_box).out(0)

            else:
                cropped = graph.node("CropMask",
                    mask=input,
                    x=bounding_box["x"],
                    y=bounding_box["y"],
                    width=cropped_width,
                    height=cropped_height,
                ).out(0)

        else:
            cropped = input

        (new_width, new_height) = cls.scale(resize_type, cropped_width, cropped_height)

        if cropped_width == new_width and cropped_height == new_height:
            resized = cropped

        else:
            assert new_width > cropped_width or new_height > cropped_height

            # It's a mask, so we have to convert it to an image.
            # This is necessary because the ResizeImageMaskNode rotates
            # masks by -90 degrees when using lanczos.
            if not is_input_image:
                image = graph.node("MaskToImage", mask=cropped).out(0)
            else:
                image = cropped

            inputs = {
                "input": image,
                "resize_type": "scale dimensions",
                "resize_type.width": new_width,
                "resize_type.height": new_height,
                "resize_type.crop": "disabled",
                "scale_method": scale_method,
            }

            resized = graph.node("ResizeImageMaskNode", **inputs).out(0)

            # We have to convert it back into a mask.
            if not is_input_image:
                resized = graph.node("ImageToMask", image=resized, channel="red").out(0)

        return io.NodeOutput(cropped, resized, expand=graph.finalize())


# @TODO Improve this after https://github.com/Comfy-Org/ComfyUI/issues/12580 is fixed
class AddAlphaToImage(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: AddAlphaToImage",
            display_name="Add Alpha To Image",
            category="image",
            description="Adds an alpha mask to an image.",
            inputs=[
                io.Image.Input("image"),
                io.Mask.Input("alpha", optional=True),
            ],
            outputs=[
                io.Image.Output(),
            ],
            enable_expand=True,
        )

    @classmethod
    def execute(cls, image, alpha) -> io.NodeOutput:
        graph = GraphBuilder()

        if alpha is not None:
            size = graph.node("GetImageSize", image=image).out(2)

            alpha = graph.node("InvertMask", mask=alpha).out(0)
            alpha = graph.node("MaskToImage", mask=alpha).out(0)
            alpha = graph.node("RepeatImageBatch", image=alpha, amount=size).out(0)
            alpha = graph.node("ImageToMask", image=alpha, channel="red").out(0)

            image = graph.node("JoinImageWithAlpha", image=image, alpha=alpha).out(0)

        return io.NodeOutput(image, expand=graph.finalize())

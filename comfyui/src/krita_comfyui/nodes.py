import textwrap
import functools
from comfy_api.latest import io
from comfy_execution.graph_utils import GraphBuilder
from shared import timestamp_local, zip_lists, serialize_any, detail_size
from shared.graph import graph_list
from .util import decode_image, decode_mask, encode_image, is_image, get_size


def always_execute():
    # Hack that causes ComfyUI to always execute the node
    # https://github.com/Comfy-Org/ComfyUI/discussions/12546
    return float("nan")


@io.comfytype(io_type="KRITA_LAYER_ID")
class LayerId(io.ComfyTypeIO):
    Type = str


@io.comfytype(io_type="KRITA_LORA")
class Lora(io.ComfyTypeIO):
    Type = dict


@io.comfytype(io_type="KRITA_SELECTION")
class Selection(io.ComfyTypeIO):
    pass


class CombineConditionings(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: CombineConditionings",
            display_name="Combine Conditionings",
            category="krita/util",
            description="Combines multiple conditionings.",
            inputs=[
                io.Conditioning.Input("conditionings"),
            ],
            outputs=[
                io.Conditioning.Output(),
            ],
            is_input_list=True,
        )

    @classmethod
    def execute(cls, conditionings) -> io.NodeOutput:
        # https://github.com/Comfy-Org/ComfyUI/blob/7cb784e0f48784bb6ed588912e186e5ee1e9ee68/nodes.py#L92
        return io.NodeOutput(functools.reduce(lambda x, y: x + y, conditionings))


class ApplyLoras(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: ApplyLoras",
            display_name="Apply Loras",
            category="krita/util",
            description="Applies loras to the model.",
            inputs=[
                io.Model.Input("model"),
                io.Clip.Input("clip"),
                Lora.Input("loras", optional=True),
            ],
            outputs=[
                io.Model.Output(is_output_list=True),
                io.Clip.Output(is_output_list=True),
            ],
            is_input_list=True,
        )

    @classmethod
    def execute(cls, model, clip, loras=[]) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


# @TODO Move this functionality into the ComfyUI CreateList node
class MakeList(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        template_matchtype = io.MatchType.Template("type")
        template_autogrow = io.Autogrow.TemplatePrefix(
            input=io.MatchType.Input("input", template=template_matchtype, optional=True),
            prefix="input",
            min=0,
            max=50,
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
            ],
        )

    @classmethod
    def execute(cls, base64, width, height) -> io.NodeOutput:
        image = decode_image(base64, width, height)
        return io.NodeOutput(image)


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
            category="krita/input",
            description="Retrieves one or more layers from Krita.",
            inputs=[
                LayerId.Input("layer_id", tooltip="The unique ID of the layer."),
                io.BoundingBox.Input("crop", optional=True, force_input=True, tooltip="Optional bounding box which will be used to crop the images and masks."),
                io.Combo.Input("mode", options=["flatten", "individual"], default="flatten", tooltip="How to process the layers.\n\n* flatten: Flattens the layers into one image.\n\n* individual: Returns each layer as an individual image."),
            ],
            outputs=[
                io.Image.Output(display_name="images", is_output_list=True),
                io.Mask.Output(display_name="masks", is_output_list=True),
                io.String.Output(display_name="names", is_output_list=True),
            ],
        )

    @classmethod
    def execute(cls, layer_id, mode, crop=None) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaCanvasImage(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaCanvasImage",
            display_name="Krita Canvas: Image",
            category="krita/input",
            description="Retrieves the canvas image from Krita.",
            inputs=[
                io.BoundingBox.Input("crop", optional=True, force_input=True, tooltip="Optional bounding box which will be used to crop the canvas image and mask."),
            ],
            outputs=[
                io.Image.Output(display_name="image"),
                io.Mask.Output(display_name="mask"),
            ],
        )

    @classmethod
    def execute(cls, crop=None) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaCanvasSize(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaCanvasSize",
            display_name="Krita Canvas: Size",
            category="krita/input",
            description="Retrieves the canvas size from Krita.",
            inputs=[],
            outputs=[
                io.Int.Output(display_name="width", tooltip="Width of the canvas."),
                io.Int.Output(display_name="height", tooltip="Height of the canvas."),
            ],
        )

    @classmethod
    def execute(cls) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaLiveMode(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaLiveMode",
            display_name="Krita Live Mode",
            category="krita/input",
            description="Retrieves the live mode information from Krita.",
            inputs=[],
            outputs=[
                io.Boolean.Output(display_name="is_enabled"),
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
            category="krita/input",
            description="Retrieves the seed from Krita.",
            inputs=[],
            outputs=[
                io.Int.Output(display_name="seed", is_output_list=True),
                io.Boolean.Output(display_name="is_fixed", is_output_list=True),
            ],
        )

    @classmethod
    def execute(cls) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaAnimationFrames(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaAnimationFrames",
            display_name="Krita Animation: Frames",
            category="krita/input",
            description="Retrieves the number of animation frames from Krita.",
            inputs=[],
            outputs=[
                io.Int.Output(display_name="frames"),
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
                io.Int.Input("round_up", min=1, default=8, tooltip="Rounds up to the nearest multiple. Set to 1 to disable rounding."),
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
                io.BoundingBox.Input("crop", optional=True, force_input=True, tooltip="Optional bounding box which will be used to crop the mask."),
            ],
            outputs=[
                io.Mask.Output(display_name="mask"),
            ],
        )

    @classmethod
    def execute(cls, selection, crop=None) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaOutput(io.ComfyNode):
    @staticmethod
    def resize_inputs():
        return [
            io.Combo.Input(
                "canvas_resize",
                default="do nothing",
                options=["do nothing", "enlarge", "crop"],
                tooltip=textwrap.dedent("""\
                    do nothing = Does nothing, the canvas stays the same size.

                    enlarge = Increases the canvas to fit the image. Never makes the canvas smaller.

                    crop = Crops the canvas to be the same size as the image.
                """),
                advanced=True,
            ),
            io.Boolean.Input(
                "resize_other_layers",
                tooltip="If true then it will resize all layers to be the same size as the image.",
                default=False,
                advanced=True,
            ),
            io.Combo.Input(
                "resize_algorithm",
                default="Bicubic",
                # This list was generated by using `Krita.filterStrategies()`
                options=["BSpline", "Mitchell", "Lanczos3", "Bell", "Bicubic", "NearestNeighbor", "Bilinear", "Hermite"],
                tooltip="Algorithm to use when resizing the layers.",
                advanced=True,
            ),
        ]

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaOutput",
            display_name="Krita Output",
            category="krita/output",
            description="Sends images to Krita.",
            inputs=[
                io.Image.Input("images", tooltip="Images that will be sent to Krita."),
                io.String.Input("name",
                    default="ComfyUI [%index%]",
                    tooltip=textwrap.dedent("""\
                        Name that will be used for the images in Krita.

                        You can use the following special syntax:

                          %index% is replaced with the index of the image.

                          %timestamp% is replaced with the current time.
                    """),
                ),

                io.Int.Input("order", default=0, tooltip="Order of the output relative to other Krita Output nodes."),
                io.Int.Input("x", default=0, tooltip="X position relative to the canvas."),
                io.Int.Input("y", default=0, tooltip="Y position relative to the canvas."),

                io.Combo.Input("batch_mode",
                    options=["separate images", "animation frames"],
                    default="separate images",
                    tooltip="How to handle multiple output images.",
                    advanced=True,
                ),

                *cls.resize_inputs(),
            ],
            outputs=[],
            is_input_list=True,
            is_output_node=True,
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return always_execute()

    @classmethod
    def execute(
        cls,
        images,
        x,
        y,
        order,
        name,
        batch_mode,
        canvas_resize,
        resize_other_layers,
        resize_algorithm,
    ) -> io.NodeOutput:
        def replace_name(name, index):
            time = timestamp_local()
            return name.replace("%index%", str(index)).replace("%timestamp%", time)

        outputs = []

        image_index = 0

        for (
            image,
            x,
            y,
            order,
            name,
            batch_mode,
            canvas_resize,
            resize_other_layers,
            resize_algorithm,
        ) in zip_lists([
            images,
            x,
            y,
            order,
            name,
            batch_mode,
            canvas_resize,
            resize_other_layers,
            resize_algorithm,
        ]):
            # https://github.com/Comfy-Org/ComfyUI/blob/ed201fff08fbbd3dbcc500b252a9f41e8051c256/comfy_extras/nodes_images.py#L576-L577
            height = image.shape[1]
            width = image.shape[2]

            for batch in image:
                outputs.append({
                    "bytes": encode_image(batch),
                    "width": width,
                    "height": height,
                    "x": x,
                    "y": y,
                    "name": replace_name(name, image_index),
                    "batch_mode": batch_mode,
                    "order": order,
                    "canvas_resize": canvas_resize,
                    "resize_other_layers": resize_other_layers,
                    "resize_algorithm": resize_algorithm,
                })

                image_index += 1

        return io.NodeOutput(ui={"krita_comfyui_output_images": outputs})


class KritaText(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaText",
            display_name="Krita Text",
            category="krita/output",
            description="Sends text to Krita.",
            inputs=[
                io.AnyType.Input("text", tooltip="Will be converted into a string and sent to Krita."),
                io.String.Input("name", default="", tooltip="Name that will be used for the text."),
                io.Int.Input("order", default=0, tooltip="Order of the output relative to other Krita Text nodes."),
            ],
            outputs=[],
            is_output_node=True,
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return always_execute()

    @classmethod
    def execute(cls, text, name, order) -> io.NodeOutput:
        return io.NodeOutput(ui={"krita_comfyui_text": [{ "name": name, "text": serialize_any(text), "order": order }]})


class KritaDebug(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaDebug",
            display_name="Krita Debug",
            category="krita/output",
            description="Sends information to Krita for debugging.",
            inputs=[
                io.Image.Input("images", tooltip="Images that will be debugged.", lazy=True, optional=True),
                io.Mask.Input("masks", tooltip="Masks that will be debugged.", lazy=True, optional=True),
                io.AnyType.Input("text", tooltip="Will be converted into a string and sent to Krita.", lazy=True, optional=True),

                io.Boolean.Input("enabled", default=False, tooltip="Whether to send debug data or not."),
                io.String.Input("name", default="", tooltip="Name that is used for the debug.", lazy=True),
                io.Int.Input("order", default=0, tooltip="Order of the output relative to other Krita Debug nodes.", lazy=True),
                io.Int.Input("x", default=0, tooltip="X position relative to the canvas.", lazy=True),
                io.Int.Input("y", default=0, tooltip="Y position relative to the canvas.", lazy=True),

                *KritaOutput.resize_inputs(),
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
    def check_lazy_status(
        cls,
        enabled,
        images=None,
        masks=None,
        text=None,
        x=None,
        y=None,
        order=None,
        name=None,
        canvas_resize=None,
        resize_other_layers=None,
        resize_algorithm=None,
    ):
        needed = []

        def check_none(list):
            try:
                return any([x is None for x in list])
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
            if order is None or check_none(order):
                needed.append("order")
            if name is None or check_none(name):
                needed.append("name")
            if canvas_resize is None or check_none(canvas_resize):
                needed.append("canvas_resize")
            if resize_other_layers is None or check_none(resize_other_layers):
                needed.append("resize_other_layers")
            if resize_algorithm is None or check_none(resize_algorithm):
                needed.append("resize_algorithm")

        return needed

    @classmethod
    def execute(
        cls,
        enabled,
        x,
        y,
        order,
        name,
        canvas_resize,
        resize_other_layers,
        resize_algorithm,
        images=[],
        masks=[],
        text=[],
    ) -> io.NodeOutput:
        graph = GraphBuilder()

        if len(images) == 0:
            images.append(None)

        if len(masks) == 0:
            masks.append(None)

        if len(text) == 0:
            text.append(None)

        outputs = {}

        for (
            enabled,
            x,
            y,
            order,
            name,
            canvas_resize,
            resize_other_layers,
            resize_algorithm,
            image,
            mask,
            text,
        ) in zip_lists([
            enabled,
            x,
            y,
            order,
            name,
            canvas_resize,
            resize_other_layers,
            resize_algorithm,
            images,
            masks,
            text,
        ]):
            if enabled:
                output = outputs.get((order, name), None)

                if output is None:
                    output = {
                        "images": [],
                        "masks": [],
                        "texts": [],
                    }

                    outputs[(order, name)] = output

                if image is not None:
                    output["images"].append({
                        "image": image,
                        "x": x,
                        "y": y,
                        "canvas_resize": canvas_resize,
                        "resize_other_layers": resize_other_layers,
                        "resize_algorithm": resize_algorithm,
                    })

                if mask is not None:
                    output["masks"].append({
                        "mask": mask,
                        "x": x,
                        "y": y,
                        "canvas_resize": canvas_resize,
                        "resize_other_layers": resize_other_layers,
                        "resize_algorithm": resize_algorithm,
                    })

                if text is not None:
                    output["texts"].append(text)


        for (order, name), output in outputs.items():
            images = output["images"]

            if len(images) > 0:
                graph.node("krita_comfyui: KritaOutput",
                    images=graph_list(graph, [image["image"] for image in images]),
                    x=graph_list(graph, [image["x"] for image in images]),
                    y=graph_list(graph, [image["y"] for image in images]),
                    order=order,
                    name=f"[DEBUG IMAGE] {name}",
                    canvas_resize=graph_list(graph, [image["canvas_resize"] for image in images]),
                    resize_other_layers=graph_list(graph, [image["resize_other_layers"] for image in images]),
                    resize_algorithm=graph_list(graph, [image["resize_algorithm"] for image in images]),
                    batch_mode="separate images",
                )

            masks = output["masks"]

            if len(masks) > 0:
                images = graph.node("MaskToImage", mask=graph_list(graph, [mask["mask"] for mask in masks])).out(0)

                graph.node("krita_comfyui: KritaOutput",
                    images=images,
                    x=graph_list(graph, [mask["x"] for mask in masks]),
                    y=graph_list(graph, [mask["y"] for mask in masks]),
                    order=order,
                    name=f"[DEBUG MASK] {name}",
                    canvas_resize=graph_list(graph, [mask["canvas_resize"] for mask in masks]),
                    resize_other_layers=graph_list(graph, [mask["resize_other_layers"] for mask in masks]),
                    resize_algorithm=graph_list(graph, [mask["resize_algorithm"] for mask in masks]),
                    batch_mode="separate images",
                )

            texts = output["texts"]

            if len(texts) > 0:
                graph.node("krita_comfyui: KritaText", text="\n\n".join([serialize_any(x) for x in texts]), name=name, order=order)

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


class DetailSize(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: DetailSize",
            display_name="Detail Size",
            category="transform",
            description="Returns the rounded size for detailing an image / mask.",
            inputs=[
                io.Int.Input("width", tooltip="The width of the image."),
                io.Int.Input("height", tooltip="The height of the image."),

                io.DynamicCombo.Input(
                    "resize_type",
                    tooltip="Select how to resize: by exact dimensions, scale factor, matching another image, etc.",
                    options=[
                        io.DynamicCombo.Option("scale total pixels", [
                            io.Float.Input("megapixels", default=1.0, min=0.0, max=16.0, step=0.01, tooltip="Target total megapixels (e.g., 1.0 ≈ 1024×1024). Aspect ratio is preserved."),
                        ]),
                    ],
                ),

                # Most models require images to be a multiple of 8.
                io.Int.Input("round_up", min=1, default=8, tooltip="Rounds up to the nearest pixel multiple. Set to 1 to disable rounding.", advanced=True),

                io.Boolean.Input("integer_multiple",
                    default=False,
                    tooltip="Rounds down to the nearest integer multiple of the original image size.\n\nThis always gives pixel-perfect results, but it also means a smaller detailing resolution.",
                    advanced=True,
                ),
            ],
            outputs=[
                io.Int.Output(display_name="width"),
                io.Int.Output(display_name="height"),
                io.Boolean.Output(display_name="is_changed", tooltip="True if the output width / height are different from the input width / height."),
            ],
        )

    @classmethod
    def execute(cls, width, height, resize_type, round_up, integer_multiple) -> io.NodeOutput:
        new_width, new_height = detail_size(width, height, resize_type, round_up, integer_multiple)

        is_changed = (new_width != width) or (new_height != height)

        return io.NodeOutput(new_width, new_height, is_changed)


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

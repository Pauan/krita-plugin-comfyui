from comfy_api.latest import io
from comfy_execution.graph_utils import GraphBuilder
from .util import timestamp, decode_image, decode_mask, encode_image, serialize_any, graph_list


def always_execute():
    # Hack that causes ComfyUI to always execute the node
    # https://github.com/Comfy-Org/ComfyUI/discussions/12546
    return float("nan")


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
    def fingerprint_inputs(cls, text):
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
    def fingerprint_inputs(cls, text):
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
    def fingerprint_inputs(cls, text):
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
    def execute(cls, enabled, x, y, name, images=None, masks=None, text=None) -> io.NodeOutput:
        assert len(enabled) == 1
        assert len(name) == 1

        graph = GraphBuilder()

        if enabled[0]:
            if images is not None and len(images) > 0:
                graph.node("krita_comfyui: KritaOutput",
                    images=graph_list(graph, images),
                    x=graph_list(graph, x),
                    y=graph_list(graph, y),
                    name=f"[DEBUG IMAGE] {name[0]} [%index%]"
                )

            if masks is not None and len(masks) > 0:
                masks = graph.node("MaskToImage", mask=graph_list(graph, masks)).out(0)

                graph.node("krita_comfyui: KritaOutput",
                    images=masks,
                    x=graph_list(graph, x),
                    y=graph_list(graph, y),
                    name=f"[DEBUG MASK] {name[0]} [%index%]"
                )

            if text is not None and len(text) > 0:
                graph.node("krita_comfyui: KritaText", text="\n".join(serialize_any(x) for x in text), name=f"[DEBUG] {name[0]}")

        return io.NodeOutput(None, expand=graph.finalize())

from comfy_api.latest import io
from .util import timestamp, decode_png, decode_png_mask, encode_png


# Hack that causes ComfyUI to always execute the node
# https://github.com/Comfy-Org/ComfyUI/discussions/12546
def always_execute():
    return float("nan")


class LoadImageBase64(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: LoadImageBase64",
            display_name="Load Image (Base64)",
            category="image",
            description="Converts a base64 string into an image.",
            inputs=[
                io.String.Input("base64", tooltip="PNG image formatted as base64"),
            ],
            outputs=[
                io.Image.Output(display_name="image"),
                io.Mask.Output(display_name="mask"),
            ],
        )

    @classmethod
    def execute(cls, base64) -> io.NodeOutput:
        (image, mask) = decode_png(base64)
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
                io.String.Input("base64", tooltip="PNG image formatted as base64"),
            ],
            outputs=[
                io.Mask.Output(display_name="mask"),
            ],
        )

    @classmethod
    def execute(cls, base64) -> io.NodeOutput:
        return io.NodeOutput(decode_png_mask(base64))


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
                io.String.Input("layer_name", tooltip="The name of the layer."),
                io.Combo.Input("mode", options=["individual", "flatten"], default="individual", tooltip="How to process the layers.\n\n* individual: Return each layer as an individual image.\n* flatten: Flatten the layers into one image."),
            ],
            outputs=[
                io.Image.Output(display_name="images", is_output_list=True),
                io.Mask.Output(display_name="masks", is_output_list=True),
                io.String.Output(display_name="names", is_output_list=True),
            ],
        )

    @classmethod
    def execute(cls, layer_name, mode) -> io.NodeOutput:
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
            category="krita",
            description="Retrieves the selection bounds from Krita.",
            inputs=[],
            outputs=[
                io.Boolean.Output(display_name="active"),
                io.Mask.Output(display_name="mask"),
                io.Int.Output(display_name="x"),
                io.Int.Output(display_name="y"),
                io.Int.Output(display_name="width"),
                io.Int.Output(display_name="height"),
            ],
        )

    @classmethod
    def execute(cls) -> io.NodeOutput:
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
    def execute(cls, images, x, y, name) -> io.NodeOutput:
        return io.NodeOutput(ui={"foo": "BAR"})


        def lookup(list, index):
            return list[min(index, len(list) - 1)]


        def replace_name(name, index):
            time = timestamp()
            return name.replace("%index%", str(index)).replace("%timestamp%", time)


        assert len(krita) == 1

        pngs = []

        list_index = 0
        image_index = 0

        for image in images:
            sub_x = lookup(x, list_index)
            sub_y = lookup(y, list_index)
            sub_name = lookup(name, list_index)

            for batch in image:
                pngs.append({
                    "png": encode_png(batch),
                    "x": sub_x,
                    "y": sub_y,
                    "name": replace_name(sub_name, image_index),
                })

                image_index += 1

            list_index += 1

        if len(pngs) > 0:
            for krita in krita:
                post(krita, "/krita-output", {
                    "images": pngs,
                })

        return io.NodeOutput()

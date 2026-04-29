import json
from comfy_api.latest import io
from .util import timestamp, decode_image, decode_mask, encode_image


@io.comfytype(io_type="KRITA_LAYER_ID")
class LayerId(io.ComfyTypeIO):
    Type = str


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
    def execute(cls, text, name) -> io.NodeOutput:
        output = ""

        if isinstance(text, str):
            output = text

        elif isinstance(text, (int, float, bool)):
            output = str(text)

        elif text is not None:
            try:
                output = json.dumps(text, indent=2)
            except:
                try:
                    output = str(text)
                except:
                    output = "Text could not be serialized."

        return io.NodeOutput(ui={"krita_comfyui_text": [{ "name": name, "text": output }]})

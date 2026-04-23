from PIL import Image
import numpy as np
import base64
import torch
import aiohttp
from io import BytesIO
from comfy_api.latest import io
from .util import timestamp


# Hack that causes ComfyUI to always execute the node
# https://github.com/Comfy-Org/ComfyUI/discussions/12546
def always_execute():
    return float("nan")


async def get(krita, path, params):
    async with krita.get(path, params=params) as response:
        json = await response.json()

    if "error" in json:
        raise RuntimeError(json["error"])

    return json


async def post(krita, path, body):
    async with krita.post(path, json=body) as response:
        json = await response.json()

    if "error" in json:
        raise RuntimeError(json["error"])

    return json


def decode_png(png):
    bytes = base64.b64decode(png)
    image = Image.open(BytesIO(bytes))

    if "A" in image.getbands():
        mask = np.array(image.getchannel("A")).astype(np.float32) / 255.0
        mask = torch.from_numpy(mask)
    else:
        # https://github.com/Comfy-Org/ComfyUI/blob/43a1263b609b923b2f69a0510bcf7ac95097e41b/comfy_extras/nodes_mask.py#L191
        mask = torch.full((1, image.height, image.width), 1.0, dtype=torch.float32, device="cpu")

    image = image.convert("RGB")
    image = np.array(image).astype(np.float32) / 255.0
    image = torch.from_numpy(image)[None,]

    return (image, mask)


def encode_png(tensor):
    array = 255.0 * tensor.cpu().numpy()
    image = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))

    with BytesIO() as output:
        image.save(output, format="png", compress_level=9, optimize=True)
        encoded = base64.b64encode(output.getvalue()).decode(encoding="utf-8")

    return encoded


# Connection to Krita
@io.comfytype(io_type="Krita")
class Krita(io.ComfyTypeIO):
    pass


class KritaConnect(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaConnect",
            display_name="Krita Connect",
            category="krita",
            description="Connects to a Krita server.",
            inputs=[
                io.String.Input("url", default="http://localhost:8321", tooltip="The URL of the Krita server."),
            ],
            outputs=[
                Krita.Output(display_name="krita"),
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, **args):
        return always_execute()

    @classmethod
    def execute(cls, url) -> io.NodeOutput:
        return io.NodeOutput(aiohttp.ClientSession(url + "/", raise_for_status=True, connector_owner=True))


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


class KritaLayers(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaLayers",
            display_name="Krita Layers",
            category="krita",
            description="Retrieves one or more layers from Krita.",
            inputs=[
                Krita.Input("krita"),

                io.String.Input("name", tooltip="The name of the layer."),
                io.Combo.Input("mode", options=["individual", "flatten"], default="individual", tooltip="How to process the layers.\n\n* individual: Return each layer as an individual image.\n* flatten: Flatten the layers into one image."),
            ],
            outputs=[
                io.Image.Output(display_name="images", is_output_list=True),
                io.Mask.Output(display_name="masks", is_output_list=True),
                io.String.Output(display_name="names", is_output_list=True),
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, **args):
        return always_execute()

    @classmethod
    async def execute(cls, krita, name, mode) -> io.NodeOutput:
        json = await get(krita, "/krita-layers", {
            "name": name,
            "mode": mode,
            "format": "png",
        })

        images = []
        masks = []
        names = []

        for info in json["images"]:
            (image, mask) = decode_png(info["png"])

            images.append(image)
            masks.append(mask)
            names.append(info["name"])

        return io.NodeOutput(images, masks, names)


class KritaCanvas(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaCanvas",
            display_name="Krita Canvas",
            category="krita",
            description="Retrieves the entire canvas from Krita.",
            inputs=[
                Krita.Input("krita"),
            ],
            outputs=[
                io.Image.Output(display_name="image"),
                io.Mask.Output(display_name="mask"),
                io.Int.Output(display_name="width"),
                io.Int.Output(display_name="height"),
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, **args):
        return always_execute()

    @classmethod
    async def execute(cls, krita) -> io.NodeOutput:
        json = await get(krita, "/krita-canvas", {
            "format": "png",
        })

        (image, mask) = decode_png(json["png"])

        return io.NodeOutput(image, mask, json["width"], json["height"])


class KritaSelection(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaSelection",
            display_name="Krita Selection",
            category="krita",
            description="Retrieves the selection bounds from Krita.",
            inputs=[
                Krita.Input("krita"),
            ],
            outputs=[
                io.Boolean.Output(display_name="active"),
                io.Int.Output(display_name="x"),
                io.Int.Output(display_name="y"),
                io.Int.Output(display_name="width"),
                io.Int.Output(display_name="height"),
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, **args):
        return always_execute()

    @classmethod
    async def execute(cls, krita) -> io.NodeOutput:
        json = await get(krita, "/krita-selection", None)

        return io.NodeOutput(json["active"], json["x"], json["y"], json["width"], json["height"])


class KritaOutput(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaOutput",
            display_name="Krita Output",
            category="krita",
            description="Sends images to Krita.",
            inputs=[
                Krita.Input("krita"),
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
    async def execute(cls, krita, images, x, y, name) -> io.NodeOutput:
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
                await post(krita, "/krita-output", {
                    "images": pngs,
                })

        return io.NodeOutput()

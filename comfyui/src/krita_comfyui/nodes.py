from PIL import Image
import numpy as np
import base64
import torch
import aiohttp
from io import BytesIO
from comfy_api.latest import io
from .util import Perf


# Hack that causes ComfyUI to always execute the node
# https://github.com/Comfy-Org/ComfyUI/discussions/12546
def always_execute():
    return float("nan")


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
                Krita.Output(),
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, **args):
        return always_execute()

    @classmethod
    def execute(cls, url) -> io.NodeOutput:
        return io.NodeOutput(aiohttp.ClientSession(url + "/", raise_for_status=True, connector_owner=True))


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
        params = {
            "name": name,
            "mode": mode,
            "format": "png",
        }

        async with krita.get("/krita-layers", params=params) as response:
            json = await response.json()

        if "error" in json:
            raise RuntimeError(json["error"])

        images = []
        masks = []
        names = []

        for info in json["images"]:
            bytes = base64.b64decode(info["png"])
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

            images.append(image)
            masks.append(mask)
            names.append(info["name"])

        return io.NodeOutput(images, masks, names)

import numpy as np
import base64
import torch
import time
import datetime
from PIL import Image
from io import BytesIO


def decode_png(png):
    bytes = base64.b64decode(png)
    image = Image.open(BytesIO(bytes))

    if "A" in image.getbands():
        mask = np.array(image.getchannel("A")).astype(np.float32) / 255.0
        mask = torch.from_numpy(mask)
    else:
        # https://github.com/Comfy-Org/ComfyUI/blob/43a1263b609b923b2f69a0510bcf7ac95097e41b/comfy_extras/nodes_mask.py#L191
        mask = torch.full((1, image.height, image.width), 1.0, dtype=torch.float32, device="cpu")

    # @TODO is this a good idea ?
    #if image.mode != "RGB":
        #image = image.convert("RGB")

    image = np.array(image).astype(np.float32) / 255.0
    image = torch.from_numpy(image)[None,]

    return (image, mask)


def decode_png_mask(png):
    bytes = base64.b64decode(png)
    image = Image.open(BytesIO(bytes))

    assert image.mode == "L"

    mask = np.array(image).astype(np.float32) / 255.0
    mask = torch.from_numpy(mask)

    return mask


def encode_png(tensor):
    array = 255.0 * tensor.cpu().numpy()
    image = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))

    with BytesIO() as output:
        image.save(output, format="png", compress_level=9, optimize=True)
        encoded = base64.b64encode(output.getvalue()).decode(encoding="utf-8")

    return encoded


def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")


class Perf:
    def __init__(self, name):
        self.name = name

    def done(self):
        end = time.perf_counter_ns()
        print("{} took {} ms".format(self.name, float(end - self.start) / 1000000.0))

    def __enter__(self):
        self.start = time.perf_counter_ns()

    async def __aenter__(self):
        self.start = time.perf_counter_ns()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.done()
        return False

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.done()
        return False

import numpy as np
import base64
import math
import torch
import time
import datetime
import json
from PIL import Image
from io import BytesIO


# https://github.com/Comfy-Org/ComfyUI/blob/dabfe73dc0e954554fe9632216149964bb9b295f/comfy_extras/nodes_images.py#L580-L589
def get_size(input):
    height = input.shape[1]
    width = input.shape[2]
    batch_size = input.shape[0]
    return (width, height, batch_size)


# https://github.com/Comfy-Org/ComfyUI/blob/dabfe73dc0e954554fe9632216149964bb9b295f/comfy_extras/nodes_post_processing.py#L267-L270
def is_image(input):
    # images have 4 dimensions: [batch, height, width, channels]
    # masks have 3 dimensions: [batch, height, width]
    return len(input.shape) == 4


def mask_inverse_sum(masks):
    return 1.0 - torch.clamp(torch.sum(torch.stack(masks, dim=0), dim=0), 0.0, 1.0)


def mask_bounds(mask):
    # TODO verify that the 3rd dimension can never break this
    _, ys, xs = torch.nonzero(mask, as_tuple=True)

    if xs.numel() == 0:
        return (0, 0, 0, 0)

    else:
        (x_min, x_max) = torch.aminmax(xs)
        (y_min, y_max) = torch.aminmax(ys)

        x_min = x_min.item()
        x_max = x_max.item() + 1

        y_min = y_min.item()
        y_max = y_max.item() + 1

        return (
            x_min,
            y_min,
            x_max - x_min,
            y_max - y_min,
        )


def zip_lists(*inputs):
    max_length = max(len(x) for x in inputs)

    for index in range(max_length):
        output = tuple(
            input[min(index, len(input) - 1)]
            for input
            in inputs
        )

        yield output


# https://stackoverflow.com/a/2189827/449477
def digits(num):
    if num == 0:
        return 1
    else:
        return int(math.log10(num)) + 1


# TODO move this into ComfyUI
def graph_list(graph, items):
    if len(items) == 1:
        return items[0]

    inputs = {}

    # We pad the numbers so that they are sorted correctly
    padding = digits(max(0, len(items) - 1))

    for i, value in enumerate(items):
        inputs["inputs.input" + str(i).zfill(padding)] = value

    return graph.node("CreateList", **inputs).out(0)


def serialize_any(text):
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

    return output


# https://github.com/Comfy-Org/ComfyUI/blob/ed201fff08fbbd3dbcc500b252a9f41e8051c256/nodes.py#L1741-L1750
def decode_image(text, width, height):
    bytes = base64.b64decode(text)
    image = Image.frombuffer("RGBA", (width, height), bytes)

    assert image.mode == "RGBA"

    mask = np.array(image.getchannel("A")).astype(np.float32) / 255.0
    mask = torch.from_numpy(mask)

    # @TODO is this a good idea ?
    #if image.mode != "RGB":
        #image = image.convert("RGB")

    image = np.array(image).astype(np.float32) / 255.0
    image = torch.from_numpy(image)[None,]

    return (image, mask)


def decode_mask(text, width, height):
    bytes = base64.b64decode(text)
    image = Image.frombuffer("L", (width, height), bytes)

    assert image.mode == "L"

    mask = np.array(image).astype(np.float32) / 255.0
    mask = torch.from_numpy(mask)

    return mask


def encode_image(tensor):
    # https://github.com/Comfy-Org/ComfyUI/blob/ed201fff08fbbd3dbcc500b252a9f41e8051c256/nodes.py#L1661-L1662
    array = 255.0 * tensor.cpu().numpy()
    array = np.clip(array, 0, 255).astype(np.uint8)
    image = Image.fromarray(array)

    if image.mode != "RGBA":
        image = image.convert("RGBA")

    return base64.b64encode(image.tobytes()).decode(encoding="utf-8")


def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")


class Perf:
    def __init__(self, name):
        self.name = name

    def done(self):
        end = time.perf_counter_ns()
        diff = float(end - self.start) / 1000000.0
        print(f"{self.name} took {diff} ms")

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

import numpy as np
import base64
import torch
import json
from PIL import Image
from io import BytesIO


# https://github.com/Comfy-Org/ComfyUI/blob/dabfe73dc0e954554fe9632216149964bb9b295f/comfy_extras/nodes_images.py#L580-L589
def get_size(input):
    if is_image(input):
        height = input.shape[1]
        width = input.shape[2]
        batch_size = input.shape[0]
    else:
        height = input.shape[0]
        width = input.shape[1]
        batch_size = 1
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


# https://github.com/Comfy-Org/ComfyUI/blob/ed201fff08fbbd3dbcc500b252a9f41e8051c256/nodes.py#L1741-L1750
def decode_image(text, width, height):
    bytes = base64.b64decode(text)
    assert len(bytes) == (width * height) * 4

    image = Image.frombuffer("RGBA", (width, height), bytes)

    assert image.width == width
    assert image.height == height
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
    assert len(bytes) == (width * height)

    image = Image.frombuffer("L", (width, height), bytes)

    assert image.width == width
    assert image.height == height
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

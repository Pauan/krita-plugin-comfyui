"""
This module contains code which is shared by both comfyui and krita.
"""
import json
import time
import math


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

    return graph.node("krita_comfyui: MakeList", **inputs).out(0)


def zip_lists(inputs):
    if len(inputs) == 1:
        for value in inputs[0]:
            yield (value,)

    else:
        min_length = min([len(x) for x in inputs])

        if min_length > 0:
            max_length = max([len(x) for x in inputs])

            for index in range(max_length):
                yield [input[min(index, len(input) - 1)] for input in inputs]


def serialize_any(text):
    if isinstance(text, str):
        return text
    else:
        try:
            return json.dumps(text, indent=2)
        except Exception:
            return str(text)


def round_to_multiple(value, multiple):
    extra = value % multiple

    if extra == 0:
        return value
    else:
        return value + (multiple - extra)


# In testing, bicubic was the highest quality algorithm for detailing.
#
# Bilinear, area, and lanczos always cause blurring.
#
# Nearest-exact is reversible and clear, but has jagged pixelation.
#
# Bicubic is technically not always reversible, but in common situations
# it is reversible, and unlike nearest-exact it isn't jagged.
def detail_size(width, height, resize_type, round_up, integer_multiple):
    type = resize_type["resize_type"]

    # https://github.com/Comfy-Org/ComfyUI/blob/7d437687c260df7772c603658111148e0e863e59/comfy_extras/nodes_post_processing.py#L281-L289
    if type == "scale by multiplier":
        multiplier = resize_type["multiplier"]

        if multiplier > 1.0:
            width = round(width * multiplier)
            height = round(height * multiplier)

    # https://github.com/Comfy-Org/ComfyUI/blob/7d437687c260df7772c603658111148e0e863e59/comfy_extras/nodes_post_processing.py#L346-L357
    elif type == "scale total pixels":
        old = float(width * height)
        new = resize_type["megapixels"] * 1024.0 * 1024.0

        if new > old:
            scale_by = math.sqrt(new / old)

            if integer_multiple:
                scale_by = math.floor(scale_by)

            width = round(width * scale_by)
            height = round(height * scale_by)

    # https://github.com/Comfy-Org/ComfyUI/blob/7d437687c260df7772c603658111148e0e863e59/comfy_extras/nodes_post_processing.py#L306-L324
    # TODO it should leave the width / height unchanged if they are smaller
    elif type == "scale longer dimension":
        largest_size = resize_type["longer_size"]

        if height > width:
            width = round((width / height) * largest_size)
            height = largest_size
        elif width > height:
            height = round((height / width) * largest_size)
            width = largest_size
        else:
            height = largest_size
            width = largest_size

    else:
        raise RuntimeError(f"Unknown resize_type {type}")

    return (
        round_to_multiple(width, round_up),
        round_to_multiple(height, round_up),
    )


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

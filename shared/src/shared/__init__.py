"""
This module contains code which is shared by both comfyui and krita.
"""
import json
import time
import math
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Generator, TypedDict, Literal, Type
from datetime import datetime, timezone


# 53-bit signed integers
# These can be safely represented as a 64-bit floating point
MIN_INTEGER: int = -9007199254740991
MAX_INTEGER: int = 9007199254740991

MIN_SEED: int = MIN_INTEGER
MAX_SEED: int = MAX_INTEGER


def timestamp_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def timestamp_local() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def zip_lists[A](inputs: list[list[A]]) -> Generator[list[A]]:
    if len(inputs) == 1:
        for value in inputs[0]:
            yield [value]

    else:
        min_length = min([len(x) for x in inputs])

        if min_length > 0:
            max_length = max([len(x) for x in inputs])

            for index in range(max_length):
                yield [input[min(index, len(input) - 1)] for input in inputs]


def serialize_any(text: object) -> str:
    if isinstance(text, str):
        return text
    else:
        try:
            return json.dumps(text, indent=2)
        except Exception:
            return str(text)


def round_to_multiple(value: int, multiple: int) -> int:
    extra = value % multiple

    if extra == 0:
        return value
    else:
        return value + (multiple - extra)


def divide_duration(duration: int, amount: int) -> tuple[int, int]:
    if duration > amount:
        bigger = int(duration / amount)
        return (
            duration - (bigger * amount),
            bigger,
        )
    else:
        return (duration, 0)


class Duration:
    def __init__(self, nanoseconds: int):
        nanoseconds, milliseconds = divide_duration(nanoseconds, 1000000)
        milliseconds, seconds = divide_duration(milliseconds, 1000)
        seconds, minutes = divide_duration(seconds, 60)
        minutes, hours = divide_duration(minutes, 60)
        hours, days = divide_duration(hours, 24)

        self.nanoseconds = nanoseconds
        self.milliseconds = milliseconds
        self.seconds = seconds
        self.minutes = minutes
        self.hours = hours
        self.days = days

    def format(self) -> str:
        output: list[str] = []

        if self.days > 0:
            if self.days == 1:
                output.append(f"{self.days} day")
            else:
                output.append(f"{self.days} days")

        if self.hours > 0:
            output.append(f"{self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}.{self.milliseconds:03d} hours")

        elif self.minutes > 0:
            output.append(f"{self.minutes:02d}:{self.seconds:02d}.{self.milliseconds:03d} minutes")

        else:
            output.append(f"{self.seconds}.{self.milliseconds:03d} seconds")

        return " and ".join(output)


def format_duration(duration: int) -> str:
    return Duration(duration).format()


class ResizeType(TypedDict):
    resize_type: Literal["scale by multiplier", "scale total pixels", "scale longer dimension"]
    multiplier: float
    megapixels: float
    longer_size: int


# In testing, bicubic was the highest quality algorithm for detailing.
#
# Bilinear, area, and lanczos always cause blurring.
#
# Nearest-exact is reversible and clear, but has jagged pixelation.
#
# Bicubic is technically not always reversible, but in common situations
# it is reversible, and unlike nearest-exact it isn't jagged.
def detail_size(width: int, height: int, resize_type: ResizeType, round_up: int, integer_multiple: bool) -> tuple[int, int]:
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


class Perf(AbstractContextManager[None]):
    def __init__(self, name: str):
        self.name = name

    def done(self):
        end = time.perf_counter_ns()
        diff = float(end - self.start) / 1000000.0
        print(f"{self.name} took {diff} ms")

    def __enter__(self):
        self.start = time.perf_counter_ns()

    async def __aenter__(self):
        self.start = time.perf_counter_ns()

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        self.done()
        return False

    async def __aexit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        self.done()
        return False

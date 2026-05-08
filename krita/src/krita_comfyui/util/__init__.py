import os
import json
import time
import re

DEBUG_ENABLED = False


NEWLINE = re.compile(r"(?:\r\n|\r|\n)")

def number_of_lines(text):
    # TODO crazy hack to get the length of an iterator
    return sum(1 for _ in re.finditer(NEWLINE, text)) + 1


def number_of_decimals(number, default=None):
    decimals = str(number)[::-1].find(".")

    if decimals == -1:
        return default
    else:
        return decimals


def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def round_to_multiple(value, multiple):
    extra = value % multiple

    if extra == 0:
        return value
    else:
        return value + (multiple - extra)


# https://en.wikipedia.org/wiki/Linear_interpolation#Programming_language_support
def lerp(percent, min, max):
    return ((1.0 - percent) * min) + (percent * max)


# Inverse lerp, finds the percentage from the value
def normalize(value, min, max):
    return (value - min) / (max - min)


def clear_logs():
    if DEBUG_ENABLED:
        # Deletes the log file
        with open("/tmp/krita.log", "w") as file:
            pass


def log_debug_json(value):
    if DEBUG_ENABLED:
        with open("/tmp/krita.log", "a") as file:
            json.dump(value, file, indent=2)
            file.write("\n\n")


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

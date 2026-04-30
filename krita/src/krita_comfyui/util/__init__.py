import os
import json
import time
import re


NEWLINE = re.compile(r"(?:\r\n|\r|\n)")

def number_of_lines(text):
    # TODO crazy hack to get the length of an iterator
    return sum(1 for _ in re.finditer(NEWLINE, text)) + 1


def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


# https://en.wikipedia.org/wiki/Linear_interpolation#Programming_language_support
def lerp(percent, min, max):
    return ((1.0 - percent) * min) + (percent * max)


# Inverse lerp, finds the percentage from the value
def normalize(value, min, max):
    return (value - min) / (max - min)


def clear_logs():
    # Deletes the log file
    with open("/tmp/krita.log", "w") as file:
        pass
    #try:
        #os.remove("/tmp/krita.log")
    #except:
        #pass


def log_debug_json(value):
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

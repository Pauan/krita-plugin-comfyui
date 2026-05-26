import datetime
import re


NEWLINE = re.compile(r"(?:\r\n|\r|\n)")

def number_of_lines(text):
    return len(list(re.finditer(NEWLINE, text))) + 1


def number_of_decimals(number, default=None):
    decimals = str(number)[::-1].find(".")

    if decimals == -1:
        return default
    else:
        return decimals


def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


# https://en.wikipedia.org/wiki/Linear_interpolation#Programming_language_support
def lerp(percent, min, max):
    return ((1.0 - percent) * min) + (percent * max)


# Inverse lerp, finds the percentage from the value
def normalize(value, min, max):
    return (value - min) / (max - min)


def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

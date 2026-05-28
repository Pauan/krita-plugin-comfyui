import re


NEWLINE = re.compile(r"(?:\r\n|\r|\n)")

def number_of_lines(text: str) -> int:
    return len(list(re.finditer(NEWLINE, text))) + 1


def number_of_decimals[A](number: int, default: A=None) -> int | A:
    decimals = str(number)[::-1].find(".")

    if decimals == -1:
        return default
    else:
        return decimals


def clamp[T: int | float](value: T, minimum: T, maximum: T) -> T:
    return max(minimum, min(value, maximum))


# https://en.wikipedia.org/wiki/Linear_interpolation#Programming_language_support
def lerp(percent: float, min: float, max: float) -> float:
    return ((1.0 - percent) * min) + (percent * max)


# Inverse lerp, finds the percentage from the value
def normalize(value: float, min: float, max: float) -> float:
    return (value - min) / (max - min)

# This module contains constant-evaluation versions of the nodes from
# https://github.com/StableLlama/ComfyUI-basic_data_handling
import math
from . import Function, Constant


def int_divide_safe(int1, int2, infinity):
    if int2 == 0:
        return infinity if int1 > 0 else -infinity
    return int1 // int2


def int_from_bytes(bytes_value, byteorder, signed):
    signed_bool = (signed == "True")
    return int.from_bytes(bytes_value, byteorder=byteorder, signed=signed_bool)


def int_to_bytes(int_value, length, byteorder, signed):
    signed_bool = (signed == "True")
    return int_value.to_bytes(length, byteorder=byteorder, signed=signed_bool)


def float_divide_safe(float1, float2):
    if float2 == 0.0:
        if float1 == 0.0:
            return float('nan')
        return float('inf') if float1 > 0 else float('-inf')
    return float1 / float2


def math_acos(value, unit):
    result = math.acos(float(value))
    if unit == "degrees":
        result = math.degrees(result)
    return result


def math_asin(value, unit):
    result = math.asin(float(value))
    if unit == "degrees":
        result = math.degrees(result)
    return result


def math_atan(value, unit):
    result = math.atan(float(value))
    if unit == "degrees":
        result = math.degrees(result)
    return result


def math_atan2(y, x, unit):
    result = math.atan2(float(y), float(x))
    if unit == "degrees":
        result = math.degrees(result)
    return result


def math_cos(angle, unit):
    if unit == "degrees":
        # Convert degrees to radians
        angle = math.radians(float(angle))
    return math.cos(float(angle))


def math_sin(angle, unit):
    if unit == "degrees":
        # Convert degrees to radians
        angle = math.radians(float(angle))
    return math.sin(float(angle))


def math_tan(angle, unit):
    if unit == "degrees":
        # Convert degrees to radians
        angle = math.radians(float(angle))

    # Handle specific angles that would result in division by zero
    if abs(math.cos(float(angle))) < 1e-10:
        raise ValueError("Tangent is undefined at this angle (division by zero)")

    return math.tan(float(angle))


def cast_to_list(input):
    if isinstance(input, list):
        return input
    return [input]


def cast_to_set(input):
    if isinstance(input, set):
        return input
    return {input,} if not isinstance(input, list) else set(input)


CONST_NODES = {
    "Basic data handling: Boolean And": Function(["input1", "input2"], lambda x, y: x and y),
    "Basic data handling: Boolean Nand": Function(["input1", "input2"], lambda x, y: not (x and y)),
    "Basic data handling: Boolean Nor": Function(["input1", "input2"], lambda x, y: not (x or y)),
    "Basic data handling: Boolean Not": Function(["input"], lambda x: not x),
    "Basic data handling: Boolean Or": Function(["input1", "input2"], lambda x, y: x or y),
    "Basic data handling: Boolean Xor": Function(["input1", "input2"], lambda x, y: x != y),

    "Basic data handling: IntCreate": Function(["value"], lambda x: int(x, 0)),
    "Basic data handling: IntCreateWithBase": Function(["value", "base"], lambda x, y: int(x, y)),
    "Basic data handling: IntAdd": Function(["int1", "int2"], lambda x, y: x + y),
    "Basic data handling: IntSubtract": Function(["int1", "int2"], lambda x, y: x - y),
    "Basic data handling: IntMultiply": Function(["int1", "int2"], lambda x, y: x * y),
    "Basic data handling: IntDivide": Function(["int1", "int2"], lambda x, y: x // y),
    "Basic data handling: IntDivideSafe": Function(["int1", "int2", "infinity"], int_divide_safe),
    "Basic data handling: IntBitCount": Function(["int_value"], lambda x: x.bit_count()),
    "Basic data handling: IntBitLength": Function(["int_value"], lambda x: x.bit_length()),
    "Basic data handling: IntFromBytes": Function(["bytes_value", "byteorder", "signed"], int_from_bytes),
    "Basic data handling: IntModulus": Function(["int1", "int2"], lambda x, y: x % y),
    "Basic data handling: IntPower": Function(["base", "exponent"], lambda x, y: x ** y),
    "Basic data handling: IntToBytes": Function(["int_value", "length", "byteorder", "signed"], int_to_bytes),

    "Basic data handling: FloatCreate": Function(["value"], lambda x: float(x)),
    "Basic data handling: FloatAdd": Function(["float1", "float2"], lambda x, y: x + y),
    "Basic data handling: FloatSubtract": Function(["float1", "float2"], lambda x, y: x - y),
    "Basic data handling: FloatMultiply": Function(["float1", "float2"], lambda x, y: x * y),
    "Basic data handling: FloatDivide": Function(["float1", "float2"], lambda x, y: x / y),
    "Basic data handling: FloatDivideSafe": Function(["float1", "float2"], float_divide_safe),
    #"Basic data handling: FloatAsIntegerRatio":
    "Basic data handling: FloatFromHex": Function(["hex_value"], lambda x: float.fromhex(x)),
    "Basic data handling: FloatHex": Function(["float_value"], lambda x: x.hex()),
    "Basic data handling: FloatIsInteger": Function(["float_value"], lambda x: x.is_integer()),
    "Basic data handling: FloatPower": Function(["base", "exponent"], lambda x, y: x ** y),
    "Basic data handling: FloatRound": Function(["float_value", "decimal_places"], lambda x, y: round(x, y)),

    "Basic data handling: MathAbs": Function(["value"], lambda x: abs(float(x))),
    "Basic data handling: MathAcos": Function(["value", "unit"], math_acos),
    "Basic data handling: MathAsin": Function(["value", "unit"], math_asin),
    "Basic data handling: MathAtan": Function(["value", "unit"], math_atan),
    "Basic data handling: MathAtan2": Function(["y", "x", "unit"], math_atan2),
    "Basic data handling: MathCeil": Function(["value"], lambda x: math.ceil(float(x))),
    "Basic data handling: MathCos": Function(["angle", "unit"], math_cos),
    "Basic data handling: MathDegrees": Function(["radians"], lambda x: math.degrees(float(x))),
    "Basic data handling: MathE": Constant(math.e),
    "Basic data handling: MathExp": Function(["value"], lambda x: math.exp(float(x))),
    "Basic data handling: MathFloor": Function(["value"], lambda x: math.floor(float(x))),
    "Basic data handling: MathLog": Function(["value", "base"], lambda value, base: math.log(float(value), float(base))),
    "Basic data handling: MathLog10": Function(["value"], lambda x: math.log10(float(x))),
    "Basic data handling: MathMax": Function(["value1", "value2"], lambda x, y: max(float(x), float(y))),
    "Basic data handling: MathMin": Function(["value1", "value2"], lambda x, y: min(float(x), float(y))),
    "Basic data handling: MathPi": Constant(math.pi),
    "Basic data handling: MathRadians": Function(["degrees"], lambda x: math.radians(float(x))),
    "Basic data handling: MathSin": Function(["angle", "unit"], math_sin),
    "Basic data handling: MathSqrt": Function(["value"], lambda x: math.sqrt(float(x))),
    "Basic data handling: MathTan": Function(["angle", "unit"], math_tan),

    "Basic data handling: CastToBoolean": Function(["input"], lambda x: bool(x)),
    "Basic data handling: CastToDict": Function(["input"], lambda x: dict(x)),
    "Basic data handling: CastToFloat": Function(["input"], lambda x: float(x)),
    "Basic data handling: CastToInt": Function(["input"], lambda x: int(x)),
    "Basic data handling: CastToList": Function(["input"], cast_to_list),
    "Basic data handling: CastToSet": Function(["input"], cast_to_set),
    "Basic data handling: CastToString": Function(["input"], lambda x: str(x)),
}

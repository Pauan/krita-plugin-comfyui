# This module contains constant-evaluation versions of the nodes from
# https://github.com/StableLlama/ComfyUI-basic_data_handling
import math
from . import ConstantNode, function, constant


@function()
class BooleanAnd(ConstantNode):
    def run(self, input1, input2):
        return input1 and input2

@function()
class BooleanNand(ConstantNode):
    def run(self, input1, input2):
        return not (input1 and input2)

@function()
class BooleanNor(ConstantNode):
    def run(self, input1, input2):
        return not (input1 or input2)

@function()
class BooleanNot(ConstantNode):
    def run(self, input):
        return not input

@function()
class BooleanOr(ConstantNode):
    def run(self, input1, input2):
        return input1 or input2

@function()
class BooleanXor(ConstantNode):
    def run(self, input1, input2):
        return input1 != input2


@function()
class IntCreate(ConstantNode):
    def run(self, value):
        return int(value, 0)

@function()
class IntCreateWithBase(ConstantNode):
    def run(self, value, base):
        return int(value, base)

@function()
class IntAdd(ConstantNode):
    def run(self, int1, int2):
        return int1 + int2

@function()
class IntSubtract(ConstantNode):
    def run(self, int1, int2):
        return int1 - int2

@function()
class IntMultiply(ConstantNode):
    def run(self, int1, int2):
        return int1 * int2

@function()
class IntDivide(ConstantNode):
    def run(self, int1, int2):
        return int1 // int2

@function()
class IntDivideSafe(ConstantNode):
    def run(self, int1, int2, infinity):
        if int2 == 0:
            return infinity if int1 > 0 else -infinity
        return int1 // int2

@function()
class IntBitCount(ConstantNode):
    def run(self, int_value):
        return int_value.bit_count()

@function()
class IntBitLength(ConstantNode):
    def run(self, int_value):
        return int_value.bit_length()

@function()
class IntFromBytes(ConstantNode):
    def run(self, bytes_value, byteorder, signed):
        signed_bool = (signed == "True")
        return int.from_bytes(bytes_value, byteorder=byteorder, signed=signed_bool)

@function()
class IntModulus(ConstantNode):
    def run(self, int1, int2):
        return int1 % int2

@function()
class IntPower(ConstantNode):
    def run(self, base, exponent):
        return base ** exponent

@function()
class IntToBytes(ConstantNode):
    def run(self, int_value, length, byteorder, signed):
        signed_bool = (signed == "True")
        return int_value.to_bytes(length, byteorder=byteorder, signed=signed_bool)


@function()
class FloatCreate(ConstantNode):
    def run(self, value):
        return float(value)

@function()
class FloatAdd(ConstantNode):
    def run(self, float1, float2):
        return float1 + float2

@function()
class FloatSubtract(ConstantNode):
    def run(self, float1, float2):
        return float1 - float2

@function()
class FloatMultiply(ConstantNode):
    def run(self, float1, float2):
        return float1 * float2

@function()
class FloatDivide(ConstantNode):
    def run(self, float1, float2):
        return float1 / float2

@function()
class FloatDivideSafe(ConstantNode):
    def run(self, float1, float2):
        if float2 == 0.0:
            if float1 == 0.0:
                return float('nan')
            return float('inf') if float1 > 0 else float('-inf')
        return float1 / float2

@function(outputs=2)
class FloatAsIntegerRatio(ConstantNode):
    def run(self, float_value):
        # Decompose the float into numerator and denominator
        numerator, denominator = float_value.as_integer_ratio()
        return (numerator, denominator)

@function()
class FloatFromHex(ConstantNode):
    def run(self, hex_value):
        return float.fromhex(hex_value)

@function()
class FloatHex(ConstantNode):
    def run(self, float_value):
        return float_value.hex()

@function()
class FloatIsInteger(ConstantNode):
    def run(self, float_value):
        return float_value.is_integer()

@function()
class FloatPower(ConstantNode):
    def run(self, base, exponent):
        return base ** exponent

@function()
class FloatRound(ConstantNode):
    def run(self, float_value, decimal_places):
        return round(float_value, decimal_places)


@function()
class MathAbs(ConstantNode):
    def run(self, value):
        return abs(float(value))

@function()
class MathAcos(ConstantNode):
    def run(self, value, unit):
        result = math.acos(float(value))
        if unit == "degrees":
            result = math.degrees(result)
        return result

@function()
class MathAsin(ConstantNode):
    def run(self, value, unit):
        result = math.asin(float(value))
        if unit == "degrees":
            result = math.degrees(result)
        return result

@function()
class MathAtan(ConstantNode):
    def run(self, value, unit):
        result = math.atan(float(value))
        if unit == "degrees":
            result = math.degrees(result)
        return result

@function()
class MathAtan2(ConstantNode):
    def run(self, y, x, unit):
        result = math.atan2(float(y), float(x))
        if unit == "degrees":
            result = math.degrees(result)
        return result

@function()
class MathCeil(ConstantNode):
    def run(self, value):
        return math.ceil(float(value))

@function()
class MathCos(ConstantNode):
    def run(self, angle, unit):
        if unit == "degrees":
            # Convert degrees to radians
            angle = math.radians(float(angle))
        return math.cos(float(angle))

@function()
class MathDegrees(ConstantNode):
    def run(self, radians):
        return math.degrees(float(radians))

@function()
class MathExp(ConstantNode):
    def run(self, value):
        return math.exp(float(value))

@function()
class MathFloor(ConstantNode):
    def run(self, value):
        return math.floor(float(value))

@function()
class MathLog(ConstantNode):
    def run(self, value, base):
        return math.log(float(value), float(base))

@function()
class MathLog10(ConstantNode):
    def run(self, value):
        return math.log10(float(value))

@function()
class MathMax(ConstantNode):
    def run(self, value1, value2):
        return max(float(value1), float(value2))

@function()
class MathMin(ConstantNode):
    def run(self, value1, value2):
        return min(float(value1), float(value2))

@function()
class MathRadians(ConstantNode):
    def run(self, degrees):
        return math.radians(float(degrees))

@function()
class MathSin(ConstantNode):
    def run(self, angle, unit):
        if unit == "degrees":
            # Convert degrees to radians
            angle = math.radians(float(angle))
        return math.sin(float(angle))

@function()
class MathSqrt(ConstantNode):
    def run(self, value):
        return math.sqrt(float(value))

@function()
class MathTan(ConstantNode):
    def run(self, angle, unit):
        if unit == "degrees":
            # Convert degrees to radians
            angle = math.radians(float(angle))

        # Handle specific angles that would result in division by zero
        if abs(math.cos(float(angle))) < 1e-10:
            raise ValueError("Tangent is undefined at this angle (division by zero)")

        return math.tan(float(angle))


@function()
class CastToBoolean(ConstantNode):
    def run(self, input):
        return bool(input)

@function()
class CastToDict(ConstantNode):
    def run(self, input):
        return dict(input)

@function()
class CastToFloat(ConstantNode):
    def run(self, input):
        return float(input)

@function()
class CastToInt(ConstantNode):
    def run(self, input):
        return int(input)

@function()
class CastToList(ConstantNode):
    def run(self, input):
        if isinstance(input, list):
            return input
        return [input]

@function()
class CastToSet(ConstantNode):
    def run(self, input):
        if isinstance(input, set):
            return input
        return {input,} if not isinstance(input, list) else set(input)

@function()
class CastToString(ConstantNode):
    def run(self, input):
        return str(input)


CONST_NODES = {
    "Basic data handling: Boolean And": BooleanAnd,
    "Basic data handling: Boolean Nand": BooleanNand,
    "Basic data handling: Boolean Nor": BooleanNor,
    "Basic data handling: Boolean Not": BooleanNot,
    "Basic data handling: Boolean Or": BooleanOr,
    "Basic data handling: Boolean Xor": BooleanXor,

    "Basic data handling: IntCreate": IntCreate,
    "Basic data handling: IntCreateWithBase": IntCreateWithBase,
    "Basic data handling: IntAdd": IntAdd,
    "Basic data handling: IntSubtract": IntSubtract,
    "Basic data handling: IntMultiply": IntMultiply,
    "Basic data handling: IntDivide": IntDivide,
    "Basic data handling: IntDivideSafe": IntDivideSafe,
    "Basic data handling: IntBitCount": IntBitCount,
    "Basic data handling: IntBitLength": IntBitLength,
    "Basic data handling: IntFromBytes": IntFromBytes,
    "Basic data handling: IntModulus": IntModulus,
    "Basic data handling: IntPower": IntPower,
    "Basic data handling: IntToBytes": IntToBytes,

    "Basic data handling: FloatCreate": FloatCreate,
    "Basic data handling: FloatAdd": FloatAdd,
    "Basic data handling: FloatSubtract": FloatSubtract,
    "Basic data handling: FloatMultiply": FloatMultiply,
    "Basic data handling: FloatDivide": FloatDivide,
    "Basic data handling: FloatDivideSafe": FloatDivideSafe,
    "Basic data handling: FloatAsIntegerRatio": FloatAsIntegerRatio,
    "Basic data handling: FloatFromHex": FloatFromHex,
    "Basic data handling: FloatHex": FloatHex,
    "Basic data handling: FloatIsInteger": FloatIsInteger,
    "Basic data handling: FloatPower": FloatPower,
    "Basic data handling: FloatRound": FloatRound,

    "Basic data handling: MathAbs": MathAbs,
    "Basic data handling: MathAcos": MathAcos,
    "Basic data handling: MathAsin": MathAsin,
    "Basic data handling: MathAtan": MathAtan,
    "Basic data handling: MathAtan2": MathAtan2,
    "Basic data handling: MathCeil": MathCeil,
    "Basic data handling: MathCos": MathCos,
    "Basic data handling: MathDegrees": MathDegrees,
    "Basic data handling: MathE": constant(math.e),
    "Basic data handling: MathExp": MathExp,
    "Basic data handling: MathFloor": MathFloor,
    "Basic data handling: MathLog": MathLog,
    "Basic data handling: MathLog10": MathLog10,
    "Basic data handling: MathMax": MathMax,
    "Basic data handling: MathMin": MathMin,
    "Basic data handling: MathPi": constant(math.pi),
    "Basic data handling: MathRadians": MathRadians,
    "Basic data handling: MathSin": MathSin,
    "Basic data handling: MathSqrt": MathSqrt,
    "Basic data handling: MathTan": MathTan,

    "Basic data handling: CastToBoolean": CastToBoolean,
    "Basic data handling: CastToDict": CastToDict,
    "Basic data handling: CastToFloat": CastToFloat,
    "Basic data handling: CastToInt": CastToInt,
    "Basic data handling: CastToList": CastToList,
    "Basic data handling: CastToSet": CastToSet,
    "Basic data handling: CastToString": CastToString,
}

# This module contains constant-evaluation versions of the built-in nodes in ComfyUI.
import math
import re
import json
import numpy
from PIL import Image
from simpleeval import simple_eval
from shared.graph import ImageView, MaskView
from . import ConstantNode, ConstantOutputs, InputValue, InputAutogrow, InputDynamicCombo, Link, function


class Primitive(ConstantNode):
    def run(self):
        return ConstantOutputs([
            self.evaluate_input("value"),
        ])


class Switch(ConstantNode):
    def run(self):
        switch = self.evaluate_input("switch")

        all_true, all_false = switch.check_booleans()

        if all_true and not all_false:
            return ConstantOutputs([
                self.evaluate_input("on_true"),
            ])

        elif all_false and not all_true:
            return ConstantOutputs([
                self.evaluate_input("on_false"),
            ])

        # We don't know if switch is true or false, so we create
        # a node and determine the branch at runtime.
        else:
            output = self.graph.node("ComfySwitchNode",
                switch=switch.to_node(self.graph),
                # Even though we don't know which branch to take,
                # we can still constant-evaluate the branches.
                on_false=self.evaluate_input("on_false").to_node(self.graph),
                on_true=self.evaluate_input("on_true").to_node(self.graph),
            ).out(0)

            return ConstantOutputs([
                Link([output]),
            ])


class Default(ConstantNode):
    def run(self):
        input = self.evaluate_input("input")

        if len(input.values) == 0:
            return ConstantOutputs([self.evaluate_input("default")])
        else:
            return ConstantOutputs([input])


class CreateList(ConstantNode):
    def run(self):
        outputs = []

        for value in self.inputs.values():
            outputs.extend(self.workflow.evaluate_link(value).values)

        return ConstantOutputs([
            Link(outputs),
        ])


class ConditioningAverage(ConstantNode):
    def run(self):
        strength = self.evaluate_input("conditioning_to_strength")

        all_zero, all_one = strength.check_percentage()

        if all_zero and not all_one:
            return ConstantOutputs([
                self.evaluate_input("conditioning_from"),
            ])

        elif all_one and not all_zero:
            return ConstantOutputs([
                self.evaluate_input("conditioning_to"),
            ])

        else:
            output = self.graph.node("ConditioningAverage",
                conditioning_to_strength=strength.to_node(self.graph),
                conditioning_to=self.evaluate_input("conditioning_to").to_node(self.graph),
                conditioning_from=self.evaluate_input("conditioning_from").to_node(self.graph),
            ).out(0)

            return ConstantOutputs([
                Link([output]),
            ])


MAX_EXPONENT = 4000

def _variadic_sum(*args):
    """Support both sum(values) and sum(a, b, c)."""
    if len(args) == 1 and hasattr(args[0], "__iter__"):
        return sum(args[0])
    return sum(args)

def _safe_pow(base, exp):
    """Wrap pow() with an exponent cap to prevent DoS via huge exponents.

    The ** operator is already guarded by simpleeval's safe_power, but
    pow() as a callable bypasses that guard.
    """
    if abs(exp) > MAX_EXPONENT:
        raise ValueError(f"Exponent {exp} exceeds maximum allowed ({MAX_EXPONENT})")
    return pow(base, exp)

MATH_FUNCTIONS = {
    "sum": _variadic_sum,
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "pow": _safe_pow,
    "sqrt": math.sqrt,
    "ceil": math.ceil,
    "floor": math.floor,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "int": int,
    "float": float,
}

@function(
    inputs={
        "values": InputAutogrow(),
    },
    outputs=3,
)
class MathExpression(ConstantNode):
    def run(self, expression, values):
        if not expression.strip():
            raise ValueError("Expression cannot be empty.")

        context: dict = dict(values)
        context["values"] = list(values.values())

        result = simple_eval(expression, names=context, functions=MATH_FUNCTIONS)
        # bool check must come first because bool is a subclass of int in Python
        if not isinstance(result, (int, float)):
            raise ValueError(
                f"Math Expression '{expression}' must evaluate to a numeric result, "
                f"got {type(result).__name__}: {result!r}"
            )
        if not math.isfinite(result):
            raise ValueError(
                f"Math Expression '{expression}' produced a non-finite result: {result}"
            )
        return float(result), int(result), bool(result)


@function()
class BoundingBox(ConstantNode):
    def run(self, x, y, width, height):
        return { "x": x, "y": y, "width": width, "height": height }


@function(
    inputs={
        "values": InputAutogrow(),
    },
)
class StringFormat(ConstantNode):
    def run(self, f_string, values):
        return f_string.format(**values)


@function()
class StringConcatenate(ConstantNode):
    def run(self, string_a, string_b, delimiter):
        return delimiter.join((string_a, string_b))


@function()
class StringSubstring(ConstantNode):
    def run(self, string, start, end):
        return string[start:end]


@function()
class StringLength(ConstantNode):
    def run(self, string):
        return len(string)


@function()
class CaseConverter(ConstantNode):
    def run(self, string, mode):
        if mode == "UPPERCASE":
            result = string.upper()
        elif mode == "lowercase":
            result = string.lower()
        elif mode == "Capitalize":
            result = string.capitalize()
        elif mode == "Title Case":
            result = string.title()
        else:
            result = string
        return result


@function()
class StringTrim(ConstantNode):
    def run(self, string, mode):
        if mode == "Both":
            result = string.strip()
        elif mode == "Left":
            result = string.lstrip()
        elif mode == "Right":
            result = string.rstrip()
        else:
            result = string
        return result


@function()
class StringReplace(ConstantNode):
    def run(self, string, find, replace):
        return string.replace(find, replace)


@function()
class StringContains(ConstantNode):
    def run(self, string, substring, case_sensitive):
        if case_sensitive:
            contains = substring in string
        else:
            contains = substring.lower() in string.lower()
        return contains


@function()
class StringCompare(ConstantNode):
    def run(self, string_a, string_b, mode, case_sensitive):
        if case_sensitive:
            a = string_a
            b = string_b
        else:
            a = string_a.lower()
            b = string_b.lower()

        if mode == "Equal":
            return a == b
        elif mode == "Starts With":
            return a.startswith(b)
        elif mode == "Ends With":
            return a.endswith(b)


@function()
class RegexMatch(ConstantNode):
    def run(self, string, regex_pattern, case_insensitive, multiline, dotall):
        flags = 0

        if case_insensitive:
            flags |= re.IGNORECASE
        if multiline:
            flags |= re.MULTILINE
        if dotall:
            flags |= re.DOTALL

        try:
            match = re.search(regex_pattern, string, flags)
            result = match is not None

        except re.error:
            result = False

        return result


@function()
class RegexExtract(ConstantNode):
    def run(self, string, regex_pattern, mode, case_insensitive, multiline, dotall, group_index):
        join_delimiter = "\n"

        flags = 0
        if case_insensitive:
            flags |= re.IGNORECASE
        if multiline:
            flags |= re.MULTILINE
        if dotall:
            flags |= re.DOTALL

        try:
            if mode == "First Match":
                match = re.search(regex_pattern, string, flags)
                if match:
                    result = match.group(0)
                else:
                    result = ""

            elif mode == "All Matches":
                matches = re.findall(regex_pattern, string, flags)
                if matches:
                    if isinstance(matches[0], tuple):
                        result = join_delimiter.join([m[0] for m in matches])
                    else:
                        result = join_delimiter.join(matches)
                else:
                    result = ""

            elif mode == "First Group":
                match = re.search(regex_pattern, string, flags)
                if match and len(match.groups()) >= group_index:
                    result = match.group(group_index)
                else:
                    result = ""

            elif mode == "All Groups":
                matches = re.finditer(regex_pattern, string, flags)
                results = []
                for match in matches:
                    if match.groups() and len(match.groups()) >= group_index:
                        results.append(match.group(group_index))
                result = join_delimiter.join(results)
            else:
                result = ""

        except re.error:
            result = ""

        return result


@function()
class RegexReplace(ConstantNode):
    def run(self, string, regex_pattern, replace, case_insensitive=True, multiline=False, dotall=False, count=0):
        flags = 0

        if case_insensitive:
            flags |= re.IGNORECASE
        if multiline:
            flags |= re.MULTILINE
        if dotall:
            flags |= re.DOTALL
        result = re.sub(regex_pattern, replace, string, count=count, flags=flags)
        return result


@function()
class JsonExtractString(ConstantNode):
    def run(self, json_string, key):
        try:
            data = json.loads(json_string)
            if isinstance(data, dict) and key in data:
                value = data[key]
                if value is None:
                    return ""

                return str(value)

            return ""

        except (json.JSONDecodeError, TypeError):
            return ""


@function()
class NotNode(ConstantNode):
    def run(self, value):
        return not value

@function(
    inputs={
        "values": InputAutogrow(),
    },
)
class AndNode(ConstantNode):
    def run(self, values):
        return all(values.values())

@function(
    inputs={
        "values": InputAutogrow(),
    },
)
class OrNode(ConstantNode):
    def run(self, values):
        return any(values.values())


@function(
    inputs_allow_links=True,
)
class RepeatLatentBatch(ConstantNode):
    def run(self, samples, amount):
        if amount == 1:
            return samples
        else:
            return self.graph.node(self.node_name, samples=samples, amount=amount).out(0)


@function(
    inputs={
        "resize_type": InputDynamicCombo(),
    },
)
class ResizeImageMaskNode(ConstantNode):
    def noop(self, input, resize_type, scale_method):
        return self.graph.node(self.node_name,
            input=input,
            scale_method=scale_method,
            **self.graph.dynamic_combo("resize_type", resize_type)
        ).out(0)


    def scale_dimensions(self, old_width, old_height, new_width, new_height):
        if new_width == 0 and new_height == 0:
            return (old_width, old_height)

        if new_width == 0:
            new_width = max(1, round(old_width * new_height / old_height))

        elif new_height == 0:
            new_height = max(1, round(old_height * new_width / old_width))

        return (new_width, new_height)


    def scale_total_pixels(self, old_width, old_height, megapixels):
        total = int(megapixels * 1024 * 1024)

        scale_by = math.sqrt(total / (old_width * old_height))

        return (
            round(old_width * scale_by),
            round(old_height * scale_by),
        )


    def resample_filter(self, scale_method):
        match scale_method:
            case "nearest-exact": return Image.Resampling.NEAREST
            case "bilinear": return Image.Resampling.BILINEAR
            case "bicubic": return Image.Resampling.BICUBIC
            case "lanczos": return Image.Resampling.LANCZOS
            case _: return None


    def resize_image(self, input, new_width, new_height, sample_filter):
        image = Image.fromarray(input._view, "RGB")

        assert image.width == input.width()
        assert image.height == input.height()
        assert image.mode == "RGB"

        return ImageView(numpy.asarray(image.resize((new_width, new_height), sample_filter)))


    def resize_mask(self, input, new_width, new_height, sample_filter):
        image = Image.fromarray(input._view, "L")

        assert image.width == input.width()
        assert image.height == input.height()
        assert image.mode == "L"

        return MaskView(numpy.asarray(image.resize((new_width, new_height), sample_filter)))


    def run(self, input, resize_type, scale_method):
        old_width = input.width()
        old_height = input.height()


        selected_type = resize_type["resize_type"]

        if selected_type == "scale by multiplier":
            multiplier = resize_type["multiplier"]
            new_width = round(old_width * multiplier)
            new_height = round(old_height * multiplier)

        elif selected_type == "scale dimensions":
            if resize_type["crop"] != "disabled":
                return self.noop(input, resize_type, scale_method)

            new_width, new_height = self.scale_dimensions(old_width, old_height, resize_type["width"], resize_type["height"])

        elif selected_type == "scale longer dimension":
            raise RuntimeError("TODO")

        elif selected_type == "scale shorter dimension":
            raise RuntimeError("TODO")

        elif selected_type == "scale width":
            new_width, new_height = self.scale_dimensions(old_width, old_height, resize_type["width"], 0)

        elif selected_type == "scale height":
            new_width, new_height = self.scale_dimensions(old_width, old_height, 0, resize_type["height"])

        elif selected_type == "scale total pixels":
            new_width, new_height = self.scale_total_pixels(old_width, old_height, resize_type["megapixels"])

        elif selected_type == "match size":
            if resize_type["crop"] != "disabled":
                return self.noop(input, resize_type, scale_method)

            match = resize_type["match"]
            new_width = match.width()
            new_height = match.height()

        elif selected_type == "scale to multiple":
            raise RuntimeError("TODO")


        if new_width == old_width and new_height == old_height:
            return input

        else:
            sample_filter = self.resample_filter(scale_method)

            if sample_filter is not None:
                if isinstance(input, ImageView):
                    return self.resize_image(input, new_width, new_height, sample_filter)

                elif isinstance(input, MaskView):
                    return self.resize_mask(input, new_width, new_height, sample_filter)

        return self.noop(input, resize_type, scale_method)


CONST_NODES = {
    # https://github.com/Comfy-Org/ComfyUI/blob/d0328b442dd2ecc27bdc112bf6452b2e96aed4f8/comfy_extras/nodes_primitive.py#L104-L108
    "PrimitiveString": Primitive,
    "PrimitiveStringMultiline": Primitive,
    "PrimitiveInt": Primitive,
    "PrimitiveFloat": Primitive,
    "PrimitiveBoolean": Primitive,

    # https://github.com/Comfy-Org/ComfyUI/blob/d0328b442dd2ecc27bdc112bf6452b2e96aed4f8/comfy_extras/nodes_images.py#L85
    "PrimitiveBoundingBox": BoundingBox,

    # https://github.com/Comfy-Org/ComfyUI/blob/d0328b442dd2ecc27bdc112bf6452b2e96aed4f8/comfy_extras/nodes_math.py#L60
    "ComfyMathExpression": MathExpression,

    # https://github.com/Comfy-Org/ComfyUI/blob/d0328b442dd2ecc27bdc112bf6452b2e96aed4f8/comfy_extras/nodes_logic.py#L11
    "ComfySwitchNode": Switch,

    # https://github.com/Comfy-Org/ComfyUI/blob/57414dadfe732b8c37754a9680c39c7fb6691437/comfy_extras/nodes_logic.py#L339-L341
    "ComfyNotNode": NotNode,
    "ComfyAndNode": AndNode,
    "ComfyOrNode": OrNode,

    # https://github.com/Comfy-Org/ComfyUI/blob/7cb784e0f48784bb6ed588912e186e5ee1e9ee68/nodes.py#L94
    "ConditioningAverage": ConditioningAverage,

    # https://github.com/Comfy-Org/ComfyUI/blob/72e3f6081ccf8853baede1308f16e0e9ebcc09dc/comfy_extras/nodes_string.py#L447-L459
    "StringFormat": StringFormat,
    "StringConcatenate": StringConcatenate,
    "StringSubstring": StringSubstring,
    "StringLength": StringLength,
    "CaseConverter": CaseConverter,
    "StringTrim": StringTrim,
    "StringReplace": StringReplace,
    "StringContains": StringContains,
    "StringCompare": StringCompare,
    "RegexMatch": RegexMatch,
    "RegexExtract": RegexExtract,
    "RegexReplace": RegexReplace,
    "JsonExtractString": JsonExtractString,

    # https://github.com/Comfy-Org/ComfyUI/blob/d0328b442dd2ecc27bdc112bf6452b2e96aed4f8/comfy_extras/nodes_toolkit.py#L6
    "CreateList": CreateList,

    # These should be moved into ComfyUI
    "krita_comfyui: Default": Default,

    "RepeatLatentBatch": RepeatLatentBatch,

    # https://github.com/Comfy-Org/ComfyUI/blob/b133e48368d0f52bb014f0dd7ae1adb7403d515b/comfy_extras/nodes_post_processing.py#L412
    "ResizeImageMaskNode": ResizeImageMaskNode,
}

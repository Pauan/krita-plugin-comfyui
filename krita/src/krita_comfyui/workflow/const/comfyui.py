# This module contains constant-evaluation versions of the built-in nodes in ComfyUI.
import math
import re
import json
from simpleeval import simple_eval
from . import Link, Function, check_booleans, zip_inputs


class Primitive:
    def get_outputs(self, workflow, node_id, node):
        return (
            workflow.evaluate_link(node["inputs"]["value"]),
        )


class Switch:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        switch = workflow.evaluate_link(inputs["switch"])

        (all_true, all_false) = check_booleans(switch.values)

        if all_true and not all_false:
            return (
                workflow.evaluate_link(inputs["on_true"]),
            )

        elif all_false and not all_true:
            return (
                workflow.evaluate_link(inputs["on_false"]),
            )

        # We don't know if switch is true or false, so we create
        # a node and determine the branch at runtime.
        else:
            output = workflow.graph.node("ComfySwitchNode",
                switch=switch.to_node(workflow.graph),
                # Even though we don't know which branch to take,
                # we can still constant-evaluate the branches.
                on_false=workflow.evaluate_link(inputs["on_false"]).to_node(workflow.graph),
                on_true=workflow.evaluate_link(inputs["on_true"]).to_node(workflow.graph),
            ).out(0)

            return (
                Link([output]),
            )


class Default:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        input = workflow.evaluate_link(inputs["input"])

        if len(input.values) == 0:
            return (workflow.evaluate_link(inputs["default"]),)
        else:
            return (input,)


class CreateList:
    def get_outputs(self, workflow, node_id, node):
        outputs = []

        for input in node["inputs"].values():
            outputs.extend(workflow.evaluate_link(input).values)

        return (
            Link(outputs),
        )


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

def execute_math_expression(expression, values):
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

class MathExpression:
    def get_outputs(self, workflow, node_id, node):
        outputs = (
            Link([]),
            Link([]),
            Link([]),
        )

        inputs = node["inputs"]

        expression = workflow.evaluate_link(inputs["expression"])
        values = workflow.evaluate_link_autogrow(inputs, "values")

        if expression.contains_link() or values.contains_link():
            node_inputs = {
                "expression": expression.to_node(workflow.graph),
            }

            values.add_to_inputs(workflow.graph, node_inputs)

            new_node = workflow.graph.node(node["class_type"], **node_inputs)

            for index, output in enumerate(outputs):
                output.values.append(new_node.out(index))

        else:
            for expression, values in zip_inputs(expression, values):
                values = execute_math_expression(expression, values)

                assert len(outputs) == len(values)

                for output, value in zip(outputs, values):
                    output.values.append(value)

        return outputs


def bounding_box(x, y, width, height):
    return { "x": x, "y": y, "width": width, "height": height }


def case_converter(string, mode):
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


def string_trim(string, mode):
    if mode == "Both":
        result = string.strip()
    elif mode == "Left":
        result = string.lstrip()
    elif mode == "Right":
        result = string.rstrip()
    else:
        result = string
    return result


def string_contains(string, substring, case_sensitive):
    if case_sensitive:
        contains = substring in string
    else:
        contains = substring.lower() in string.lower()
    return contains


def string_compare(string_a, string_b, mode, case_sensitive):
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


def regex_match(string, regex_pattern, case_insensitive, multiline, dotall):
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


def regex_extract(string, regex_pattern, mode, case_insensitive, multiline, dotall, group_index):
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


def regex_replace(string, regex_pattern, replace, case_insensitive=True, multiline=False, dotall=False, count=0):
    flags = 0

    if case_insensitive:
        flags |= re.IGNORECASE
    if multiline:
        flags |= re.MULTILINE
    if dotall:
        flags |= re.DOTALL
    result = re.sub(regex_pattern, replace, string, count=count, flags=flags)
    return result


def json_extract_string(json_string, key):
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


CONST_NODES = {
    #https://github.com/Comfy-Org/ComfyUI/blob/d0328b442dd2ecc27bdc112bf6452b2e96aed4f8/comfy_extras/nodes_primitive.py#L104-L108
    "PrimitiveString": Primitive(),
    "PrimitiveStringMultiline": Primitive(),
    "PrimitiveInt": Primitive(),
    "PrimitiveFloat": Primitive(),
    "PrimitiveBoolean": Primitive(),

    # https://github.com/Comfy-Org/ComfyUI/blob/d0328b442dd2ecc27bdc112bf6452b2e96aed4f8/comfy_extras/nodes_images.py#L85
    "PrimitiveBoundingBox": Function(["x", "y", "width", "height"], bounding_box),

    # https://github.com/Comfy-Org/ComfyUI/blob/d0328b442dd2ecc27bdc112bf6452b2e96aed4f8/comfy_extras/nodes_math.py#L60
    "ComfyMathExpression": MathExpression(),

    # https://github.com/Comfy-Org/ComfyUI/blob/d0328b442dd2ecc27bdc112bf6452b2e96aed4f8/comfy_extras/nodes_logic.py#L11
    "ComfySwitchNode": Switch(),

    # https://github.com/Comfy-Org/ComfyUI/blob/d0328b442dd2ecc27bdc112bf6452b2e96aed4f8/comfy_extras/nodes_string.py#L416-L427
    "StringConcatenate": Function(["string_a", "string_b", "delimiter"], lambda a, b, c: c.join((a, b))),
    "StringSubstring": Function(["string", "start", "end"], lambda string, start, end: string[start:end]),
    "StringLength": Function(["string"], lambda string: len(string)),
    "CaseConverter": Function(["string", "mode"], case_converter),
    "StringTrim": Function(["string", "mode"], string_trim),
    "StringReplace": Function(["string", "find", "replace"], lambda a, b, c: a.replace(b, c)),
    "StringContains": Function(["string", "substring", "case_sensitive"], string_contains),
    "StringCompare": Function(["string_a", "string_b", "mode", "case_sensitive"], string_compare),
    "RegexMatch": Function(["string", "regex_pattern", "case_insensitive", "multiline", "dotall"], regex_match),
    "RegexExtract": Function(["string", "regex_pattern", "mode", "case_insensitive", "multiline", "dotall", "group_index"], regex_extract),
    "RegexReplace": Function(["string", "regex_pattern", "replace", "case_insensitive", "multiline", "dotall", "count"], regex_replace),
    "JsonExtractString": Function(["json_string", "key"], json_extract_string),

    # https://github.com/Comfy-Org/ComfyUI/blob/d0328b442dd2ecc27bdc112bf6452b2e96aed4f8/comfy_extras/nodes_toolkit.py#L6
    "CreateList": CreateList(),

    # These should be moved into ComfyUI
    "krita_comfyui: Default": Default(),
}

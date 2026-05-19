# This module contains constant-evaluation versions of the built-in nodes in ComfyUI.
import math
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

    # https://github.com/Comfy-Org/ComfyUI/blob/d0328b442dd2ecc27bdc112bf6452b2e96aed4f8/comfy_extras/nodes_string.py#L8
    "StringConcatenate": Function(["string_a", "string_b", "delimiter"], lambda a, b, c: c.join((a, b))),

    # https://github.com/Comfy-Org/ComfyUI/blob/d0328b442dd2ecc27bdc112bf6452b2e96aed4f8/comfy_extras/nodes_toolkit.py#L6
    "CreateList": CreateList(),

    # These should be moved into ComfyUI
    "krita_comfyui: Default": Default(),
}

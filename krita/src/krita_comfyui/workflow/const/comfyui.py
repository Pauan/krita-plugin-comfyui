# This module contains constant-evaluation versions of the built-in nodes in ComfyUI.
from . import Link, Function, check_booleans


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


CONST_NODES = {
    "PrimitiveString": Primitive(),
    "PrimitiveStringMultiline": Primitive(),
    "PrimitiveInt": Primitive(),
    "PrimitiveFloat": Primitive(),
    "PrimitiveBoolean": Primitive(),
    "ComfySwitchNode": Switch(),
    "krita_comfyui: Default": Default(),
    "StringConcatenate": Function(["string_a", "string_b", "delimiter"], lambda a, b, c: c.join((a, b))),
}

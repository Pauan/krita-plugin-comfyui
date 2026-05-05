from . import Link, zip_inputs


class Switch:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        switch = workflow.evaluate_link(inputs["switch"])
        on_true = workflow.evaluate_link(inputs["on_true"])
        on_false = workflow.evaluate_link(inputs["on_false"])

        outputs = []

        for (switch, on_true, on_false) in zip_inputs(switch, on_true, on_false):
            if isinstance(switch, bool):
                if switch:
                    outputs.append(on_true)
                else:
                    outputs.append(on_false)

            # We don't know if switch is true or false, so we create
            # a node and determine the branch at runtime.
            else:
                outputs.append(workflow.graph.node("ComfySwitchNode",
                    switch=switch,
                    # Even though we don't know which branch to take,
                    # the branches are still constant-evaluated.
                    on_false=on_false,
                    on_true=on_true,
                ).out(0))

        return (
            Link(outputs),
        )

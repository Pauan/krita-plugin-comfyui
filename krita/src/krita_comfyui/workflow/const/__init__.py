def zip_lists(*inputs):
    if len(inputs) == 1:
        for value in inputs[0]:
            yield (value,)

    else:
        min_length = min(len(x) for x in inputs)

        if min_length > 0:
            max_length = max(len(x) for x in inputs)

            for index in range(max_length):
                yield tuple(input[min(index, len(input) - 1)] for input in inputs)


def zip_inputs(*inputs):
    yield from zip_lists(*(x.values for x in inputs))


def is_link(value):
    return isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and isinstance(value[1], int)


def check_booleans(inputs):
    all_true = True
    all_false = True

    for condition in inputs:
        if isinstance(condition, bool):
            if condition:
                all_false = False
            else:
                all_true = False
        else:
            all_true = False
            all_false = False

    return (all_true, all_false)


class WorkflowError(RuntimeError):
    pass


class Link:
    def __init__(self, values):
        assert isinstance(values, list)

        # List of values
        self.values = values

        self.node = None

    # Converts the Link into a graph node.
    #
    # This is cached, so calling it multiple times gives the same node.
    def to_node(self, graph):
        if self.node is None:
            self.node = graph.list(self.values)
        return self.node


class Function:
    def __init__(self, inputs, evaluate):
        self.inputs = inputs
        self.evaluate = evaluate

    def get_outputs(self, workflow, node_id, node):
        node_name = node["class_type"]
        inputs = node["inputs"]

        links = tuple(workflow.evaluate_link(inputs[name]) for name in self.inputs)
        outputs = []

        for values in zip_inputs(*links):
            # All links are constant values, so we can call the function.
            if all(not is_link(value) for value in values):
                outputs.append(self.evaluate(*values))

            else:
                node_inputs = {}

                assert len(self.inputs) == len(values)

                for name, value in zip(self.inputs, values):
                    node_inputs[name] = value

                outputs.append(workflow.graph.node(node_name, **node_inputs).out(0))

        return (
            Link(outputs),
        )

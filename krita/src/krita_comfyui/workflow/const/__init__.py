def zip_lists(inputs):
    min_length = min(len(x) for x in inputs)

    if min_length > 0:
        max_length = max(len(x) for x in inputs)

        for index in range(max_length):
            yield tuple(input[min(index, len(input) - 1)] for input in inputs)


def zip_inputs(*inputs):
    yield from zip_lists([x.values for x in inputs])


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

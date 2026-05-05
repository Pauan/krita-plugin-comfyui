def zip_lists(inputs):
    max_length = max(len(x) for x in inputs)

    for index in range(max_length):
        output = tuple(
            input[min(index, len(input) - 1)]
            for input
            in inputs
        )

        yield output

def zip_inputs(*inputs):
    yield from zip_lists([x.values for x in inputs])


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

from ...shared import zip_lists


def zip_dict(input):
    outputs = []

    items = input.items()

    keys = [x[0] for x in items]

    for values in zip_lists([x[1].values for x in items]):
        assert len(keys) == len(values)
        outputs.append(dict(zip(keys, values)))

    return outputs


def is_link(value):
    return isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and isinstance(value[1], int)


class WorkflowError(RuntimeError):
    pass


class OutputsBase:
    def lookup_index(self, index):
        pass


class NodeOutputs(OutputsBase):
    def __init__(self, node):
        self.node = node

    def lookup_index(self, index):
        return Link([self.node.out(index)])


class ConstantOutputs(OutputsBase):
    def __init__(self, links):
        self.links = links


    @staticmethod
    def empty(amount):
        return ConstantOutputs([Link([]) for _ in range(0, amount)])


    def lookup_index(self, index):
        return self.links[index]


    def node(self, node):
        for index, link in enumerate(self.links):
            link.values.append(node.out(index))


    def append(self, values):
        assert len(self.links) == len(values)

        for link, value in zip(self.links, values):
            link.values.append(value)


    def extend(self, values):
        assert len(self.links) == len(values)

        for link, value in zip(self.links, values):
            link.values.extend(value)


class Link:
    def __init__(self, values):
        assert isinstance(values, list)

        # List of values
        self.values = values

        self.node = None


    # Returns true if at least one of the values is a link.
    def contains_link(self):
        for value in self.values:
            if is_link(value):
                return True
        return False


    def transform(self, f):
        self.values = [f(value) for value in self.values]


    # Checks if all of the values are true or false.
    def check_booleans(self):
        all_true = True
        all_false = True

        for condition in self.values:
            if isinstance(condition, bool):
                if condition:
                    all_false = False
                else:
                    all_true = False
            else:
                all_true = False
                all_false = False

        return (all_true, all_false)


    # Converts the Link into a graph node.
    #
    # This is cached, so calling it multiple times gives the same node.
    def to_node(self, graph):
        if self.node is None:
            self.node = graph.list(self.values)
        return self.node


class LinkAutogrow(Link):
    def __init__(self, links, prefix):
        super().__init__(zip_dict(links))
        self.prefix = prefix
        self.links = links


    def contains_link(self):
        for link in self.links.values():
            if link.contains_link():
                return True
        return False


    def transform(self, f):
        for link in self.links.values():
            link.transform(f)


    def add_to_dict(self, graph, dict):
        for key, link in self.links.items():
            dict[self.prefix + key] = link.to_node(graph)


class LinkDynamicCombo(Link):
    def __init__(self, links, name, prefix):
        super().__init__(zip_dict(links))
        self.name = name
        self.prefix = prefix
        self.links = links


    def contains_link(self):
        for link in self.links.values():
            if link.contains_link():
                return True
        return False


    def transform(self, f):
        for link in self.links.values():
            link.transform(f)


    def add_to_dict(self, graph, dict):
        for key, link in self.links.items():
            if key == self.name:
                dict[key] = link.to_node(graph)
            else:
                dict[self.prefix + key] = link.to_node(graph)


class Input:
    def __init__(self, *, constant=False, optional=False, allow_links=False, raw_link=False):
        # If true then it will error if the input has links.
        self.constant = constant

        # If true then the input is optional. It will be None if it doesn't exist.
        self.optional = optional

        # If true then the function will run even if the input has links.
        self.allow_links = allow_links

        # If true then the function is given the Link object instead of the values of the link.
        self.raw_link = raw_link


class InputValue(Input):
    def get_link(self, input_name, const_node):
        link = const_node.evaluate_input(input_name, optional=self.optional)

        if link is None:
            return Link([None])

        if self.constant:
            const_node.assert_constant(input_name, link)

        return link


    def add_to_dict(self, input_name, const_node, link, dict):
        dict[input_name] = link.to_node(const_node.graph)


class InputAutogrow(Input):
    def get_link(self, input_name, const_node):
        prefix = f"{input_name}."

        links = {}

        for key, value in const_node.inputs.items():
            name = key.removeprefix(prefix)

            if name != key:
                link = const_node.workflow.evaluate_link(value)

                if self.constant:
                    const_node.assert_constant(input_name, link)

                links[name] = link

        link = LinkAutogrow(links, prefix)

        if len(link.values) == 0:
            if self.optional:
                link.values.append(None)
            else:
                const_node.error(f"{input_name} is missing")

        return link


    def add_to_dict(self, input_name, const_node, link, dict):
        link.add_to_dict(const_node.graph, dict)


class InputDynamicCombo(Input):
    def get_link(self, input_name, const_node):
        prefix = f"{input_name}."

        links = {}

        for key, value in const_node.inputs.items():
            if key == input_name:
                link = const_node.workflow.evaluate_link(value)

                if self.constant:
                    const_node.assert_constant(input_name, link)

                links[input_name] = link

            else:
                name = key.removeprefix(prefix)

                if name != key:
                    link = const_node.workflow.evaluate_link(value)

                    if self.constant:
                        const_node.assert_constant(input_name, link)

                    links[name] = link

        link = LinkDynamicCombo(links, input_name, prefix)

        if len(link.values) == 0:
            if self.optional:
                link.values.append(None)
            else:
                const_node.error(f"{input_name} is missing")

        return link


    def add_to_dict(self, input_name, const_node, link, dict):
        link.add_to_dict(const_node.graph, dict)


# Base class for all nodes that can be constant evaluated.
class ConstantNode:
    def __init__(self, workflow, node_id, node):
        self.workflow = workflow
        self.graph = self.workflow.graph
        self.node_id = node_id
        self.node = node
        self.inputs = node["inputs"]


    @property
    def node_name(self):
        return self.node["class_type"]


    def evaluate_input(self, name, *, optional=False):
        if optional:
            try:
                input = self.inputs[name]
            except KeyError:
                return None
        else:
            input = self.inputs[name]

        return self.workflow.evaluate_link(input)


    def error(self, message):
        raise WorkflowError(f"[#{self.node_id} {self.NAME}]\n{message}")


    def assert_constant(self, input_name, link):
        if link.contains_link():
            self.error(f"{input_name} must be constant")


    def run(self):
        pass


# Single constant value.
def constant(value):
    class Constant(ConstantNode):
        def run(self):
            return ConstantOutputs([
                Link([value]),
            ])

    return Constant


def get_input(inputs, name, constant, allow_links):
    try:
        input = inputs[name]

        if constant:
            input.constant = True

        if allow_links:
            input.allow_links = True

        return input

    except KeyError:
        return InputValue(constant=constant, allow_links=allow_links)


# Creates an optimized ConstantNode.
#
# By dynamically creating classes it's able to have faster performance because it
# can personalize each class to the situation.
def function(*,
    # Name used for error messages.
    name=None,

    # Dictionary of information for inputs.
    inputs=None,

    # Number of outputs.
    outputs=1,

    # Forces all inputs to be constant.
    inputs_constant=False,

    # Allows for the function to run even if there are links in the inputs.
    inputs_allow_links=False,

    # If true, the input variables are a list of values.
    is_input_list=False,

    # If true, the function must return a list of values.
    is_output_list=False,
):
    def wrapper(cls):
        assert issubclass(cls, ConstantNode)

        debug_name = name

        code = cls.run.__code__

        # Extracts the argument names of the run method.
        arg_names = code.co_varnames

        assert arg_names[0] == "self"

        arg_names = arg_names[1:code.co_argcount]

        if inputs is None:
            inputs_list = [(name, InputValue(constant=inputs_constant, allow_links=inputs_allow_links)) for name in arg_names]
        else:
            inputs_list = [(name, get_input(inputs, name, inputs_constant, inputs_allow_links)) for name in arg_names]


        if is_input_list:
            def zip_inputs(values):
                return [values]
        else:
            def zip_inputs(values):
                return zip_lists(values)


        if len(inputs_list) == 0:
            def iter_inputs(cls, out):
                return [[]]

        elif all([(input.constant or input.allow_links) for name, input in inputs_list]):
            def iter_inputs(cls, out):
                values = []

                for name, input in inputs_list:
                    link = input.get_link(name, cls)

                    if input.raw_link:
                        values.append(link)
                    else:
                        values.append(link.values)

                return zip_inputs(values)

        else:
            def iter_inputs(cls, out):
                links = []
                values = []

                contains_link = False

                for name, input in inputs_list:
                    link = input.get_link(name, cls)

                    if (not input.constant) and (not input.allow_links) and link.contains_link():
                        contains_link = True

                    links.append(link)

                    if not contains_link:
                        if input.raw_link:
                            values.append(link)
                        else:
                            values.append(link.values)

                # Because a link can potentially be multiple values, and we have no way
                # of knowing at compile-time how many values that link has, if there is
                # even a single link then we cannot constant evaluate the node.
                if contains_link:
                    node_inputs = {}

                    # We can still constant evaluate the links as much as possible, but
                    # the node itself will be evaluated at runtime.
                    for (name, input), link in zip(inputs_list, links):
                        input.add_to_dict(name, cls, link, node_inputs)

                    out.add_node(cls.graph.node(cls.node_name, **node_inputs))
                    return []

                return zip_inputs(values)


        if outputs == 1:
            class Outputs:
                def __init__(self):
                    self.results = []

                def add_node(self, node):
                    self.results.append(node.out(0))

                def add_results(self, results):
                    if is_output_list:
                        self.results.extend(results)
                    else:
                        self.results.append(results)

                def finalize(self):
                    return ConstantOutputs([
                        Link(self.results),
                    ])

        else:
            class Outputs:
                def __init__(self):
                    self.links = [Link([]) for _ in range(0, outputs)]

                def add_node(self, node):
                    for index, link in enumerate(self.links):
                        link.values.append(node.out(index))

                def add_results(self, results):
                    assert len(self.links) == len(results)

                    if is_output_list:
                        for link, result in zip(self.links, results):
                            link.values.extend(result)

                    else:
                        for link, result in zip(self.links, results):
                            link.values.append(result)

                def finalize(self):
                    return ConstantOutputs(self.links)


        class Function(cls):
            NAME = debug_name

            def run(self):
                out = Outputs()

                for values in iter_inputs(self, out):
                    out.add_results(super().run(*values))

                return out.finalize()

        return Function

    return wrapper

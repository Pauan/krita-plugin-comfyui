from __future__ import annotations

from typing import Any, Literal, NoReturn, cast, overload
from collections.abc import Callable, Sequence
from shared import zip_lists
from shared.graph import Graph, NodeOutputs as GraphNodeOutputs
from ..graph import WorkflowGraph


def zip_dict(input: dict[str, Link]) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []

    items = input.items()

    keys = [x[0] for x in items]

    for values in zip_lists([x[1].values for x in items]):
        assert len(keys) == len(values)
        outputs.append(dict(zip(keys, values)))

    return outputs


def is_link(value: Any) -> bool:
    if not isinstance(value, list):
        return False

    items = cast(list[Any], value)
    return len(items) == 2 and isinstance(items[0], str) and isinstance(items[1], int)


class WorkflowError(RuntimeError):
    pass


class OutputsBase:
    def lookup_index(self, index: int) -> Link:
        raise NotImplementedError


class NodeOutputs(OutputsBase):
    def __init__(self, node: GraphNodeOutputs) -> None:
        self.node = node

    def lookup_index(self, index: int) -> Link:
        return Link([self.node.out(index)])


class ConstantOutputs(OutputsBase):
    def __init__(self, links: list[Link]) -> None:
        self.links = links


    @staticmethod
    def empty(amount: int) -> ConstantOutputs:
        return ConstantOutputs([Link([]) for _ in range(0, amount)])


    def lookup_index(self, index: int) -> Link:
        return self.links[index]


    def node(self, node: GraphNodeOutputs) -> None:
        for index, link in enumerate(self.links):
            link.values.append(node.out(index))


    def append(self, values: Sequence[Any]) -> None:
        assert len(self.links) == len(values)

        for link, value in zip(self.links, values):
            link.values.append(value)


    def extend(self, values: Sequence[Sequence[Any]]) -> None:
        assert len(self.links) == len(values)

        for link, value in zip(self.links, values):
            link.values.extend(value)


class Link:
    def __init__(self, values: list[Any]) -> None:
        assert isinstance(values, list)

        # List of values
        self.values = values

        self.node: Any = None


    # Returns true if at least one of the values is a link.
    def contains_link(self) -> bool:
        for value in self.values:
            if is_link(value):
                return True
        return False


    def transform(self, f: Callable[[Any], Any]) -> None:
        self.values = [f(value) for value in self.values]


    def map(self, f: Callable[[Any], Any]) -> Link:
        return Link([f(value) for value in self.values])


    # Checks if all of the values are true or false.
    def check_booleans(self) -> tuple[bool, bool]:
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


    # Checks if all of the values are 0.0 or 1.0
    def check_percentage(self) -> tuple[bool, bool]:
        all_zero = True
        all_one = True

        for value in self.values:
            if isinstance(value, float):
                if value == 0.0:
                    all_one = False
                elif value == 1.0:
                    all_zero = False
                else:
                    all_zero = False
                    all_one = False
            else:
                all_zero = False
                all_one = False

        return (all_zero, all_one)


    # Converts the Link into a graph node.
    #
    # This is cached, so calling it multiple times gives the same node.
    def to_node(self, graph: Graph) -> Any:
        if self.node is None:
            self.node = graph.list(self.values)
        return self.node


class LinkAutogrow(Link):
    def __init__(self, links: dict[str, Link], prefix: str) -> None:
        super().__init__(zip_dict(links))
        self.prefix = prefix
        self.links = links


    def contains_link(self) -> bool:
        for link in self.links.values():
            if link.contains_link():
                return True
        return False


    def transform(self, f: Callable[[Any], Any]) -> None:
        for link in self.links.values():
            link.transform(f)


    def add_to_dict(self, graph: Graph, dict: dict[str, Any]) -> None:
        for key, link in self.links.items():
            dict[self.prefix + key] = link.to_node(graph)


class LinkDynamicCombo(Link):
    def __init__(self, links: dict[str, Link], name: str, prefix: str) -> None:
        super().__init__(zip_dict(links))
        self.name = name
        self.prefix = prefix
        self.links = links


    def contains_link(self) -> bool:
        for link in self.links.values():
            if link.contains_link():
                return True
        return False


    def transform(self, f: Callable[[Any], Any]) -> None:
        for link in self.links.values():
            link.transform(f)


    def add_to_dict(self, graph: Graph, dict: dict[str, Any]) -> None:
        for key, link in self.links.items():
            if key == self.name:
                dict[key] = link.to_node(graph)
            else:
                dict[self.prefix + key] = link.to_node(graph)


class Input:
    def __init__(self, *, constant: bool = False, optional: bool = False, allow_links: bool = False, raw_link: bool = False) -> None:
        # If true then it will error if the input has links.
        self.constant = constant

        # If true then the input is optional. It will be None if it doesn't exist.
        self.optional = optional

        # If true then the function will run even if the input has links.
        self.allow_links = allow_links

        # If true then the function is given the Link object instead of the values of the link.
        self.raw_link = raw_link

    def get_link(self, input_name: str, const_node: ConstantNode) -> Link:
        raise NotImplementedError

    def add_to_dict(self, input_name: str, const_node: ConstantNode, link: Link, dict: dict[str, Any]) -> None:
        raise NotImplementedError


class InputValue(Input):
    def get_link(self, input_name: str, const_node: ConstantNode) -> Link:
        link = const_node.evaluate_input(input_name, optional=self.optional)

        if link is None:
            return Link([None])

        if self.constant:
            const_node.assert_constant(input_name, link)

        return link


    def add_to_dict(self, input_name: str, const_node: ConstantNode, link: Link, dict: dict[str, Any]) -> None:
        dict[input_name] = link.to_node(const_node.graph)


class InputAutogrow(Input):
    def get_link(self, input_name: str, const_node: ConstantNode) -> Link:
        prefix = f"{input_name}."

        links: dict[str, Link] = {}

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


    def add_to_dict(self, input_name: str, const_node: ConstantNode, link: Link, dict: dict[str, Any]) -> None:
        cast(LinkAutogrow | LinkDynamicCombo, link).add_to_dict(const_node.graph, dict)


class InputDynamicCombo(Input):
    def get_link(self, input_name: str, const_node: ConstantNode) -> Link:
        prefix = f"{input_name}."

        links: dict[str, Link] = {}

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


    def add_to_dict(self, input_name: str, const_node: ConstantNode, link: Link, dict: dict[str, Any]) -> None:
        cast(LinkAutogrow | LinkDynamicCombo, link).add_to_dict(const_node.graph, dict)


# Base class for all nodes that can be constant evaluated.
class ConstantNode:
    NAME: str | None

    def __init__(self, workflow: WorkflowGraph, node_id: str, node: dict[str, Any]) -> None:
        self.workflow = workflow
        self.graph = self.workflow.graph
        self.node_id = node_id
        self.node = node
        self.inputs = node["inputs"]


    @property
    def node_name(self) -> str:
        return self.node["class_type"]


    @overload
    def evaluate_input(self, name: str, *, optional: Literal[False] = False) -> Link: ...
    @overload
    def evaluate_input(self, name: str, *, optional: bool) -> Link | None: ...
    def evaluate_input(self, name: str, *, optional: bool = False) -> Link | None:
        if optional:
            try:
                input = self.inputs[name]
            except KeyError:
                return None
        else:
            input = self.inputs[name]

        return self.workflow.evaluate_link(input)


    def error(self, message: str) -> NoReturn:
        raise WorkflowError(f"[#{self.node_id} {self.NAME}]\n{message}")


    def assert_constant(self, input_name: str, link: Link) -> None:
        if link.contains_link():
            self.error(f"{input_name} must be constant")


    def run(self, *args: Any, **kwargs: Any) -> Any:
        pass


# Single constant value.
def constant(value: Any) -> type[ConstantNode]:
    class Constant(ConstantNode):
        def run(self) -> ConstantOutputs:
            return ConstantOutputs([
                Link([value]),
            ])

    return Constant


def get_input(inputs: dict[str, Input], name: str, constant: bool, allow_links: bool) -> Input:
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
    name: str | None = None,

    # Dictionary of information for inputs.
    inputs: dict[str, Input] | None = None,

    # Number of outputs.
    outputs: int = 1,

    # Forces all inputs to be constant.
    inputs_constant: bool = False,

    # Allows for the function to run even if there are links in the inputs.
    inputs_allow_links: bool = False,

    # If true, the input variables are a list of values.
    is_input_list: bool = False,

    # If true, the function must return a list of values.
    is_output_list: bool = False,
) -> Callable[[type[ConstantNode]], type[ConstantNode]]:
    def wrapper(cls: type[ConstantNode]) -> type[ConstantNode]:
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
            def zip_inputs(values: list[Any]) -> Any:
                return [values]
        else:
            def zip_inputs(values: list[Any]) -> Any:
                return zip_lists(values)


        if len(inputs_list) == 0:
            def iter_inputs(cls: ConstantNode, out: Any) -> Any:
                return [[]]

        elif all([(input.constant or input.allow_links) for _, input in inputs_list]):
            def iter_inputs(cls: ConstantNode, out: Any) -> Any:
                values: list[Any] = []

                for name, input in inputs_list:
                    link = input.get_link(name, cls)

                    if input.raw_link:
                        values.append(link)
                    else:
                        values.append(link.values)

                return zip_inputs(values)

        else:
            def iter_inputs(cls: ConstantNode, out: Any) -> Any:
                links: list[Link] = []
                values: list[Any] = []

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
                    node_inputs: dict[str, Any] = {}

                    # We can still constant evaluate the links as much as possible, but
                    # the node itself will be evaluated at runtime.
                    for (name, input), link in zip(inputs_list, links):
                        input.add_to_dict(name, cls, link, node_inputs)

                    out.add_node(cls.graph.node(cls.node_name, **node_inputs))
                    return []

                return zip_inputs(values)


        Outputs: type[Any]

        if outputs == 1:
            class SingleOutputs:
                def __init__(self) -> None:
                    self.results: list[Any] = []

                def add_node(self, node: GraphNodeOutputs) -> None:
                    self.results.append(node.out(0))

                def add_results(self, results: Any) -> None:
                    if is_output_list:
                        self.results.extend(results)
                    else:
                        self.results.append(results)

                def finalize(self) -> ConstantOutputs:
                    return ConstantOutputs([
                        Link(self.results),
                    ])

            Outputs = SingleOutputs

        else:
            class MultiOutputs:
                def __init__(self) -> None:
                    self.links = [Link([]) for _ in range(0, outputs)]

                def add_node(self, node: GraphNodeOutputs) -> None:
                    for index, link in enumerate(self.links):
                        link.values.append(node.out(index))

                def add_results(self, results: Any) -> None:
                    assert len(self.links) == len(results)

                    if is_output_list:
                        for link, result in zip(self.links, results):
                            link.values.extend(result)

                    else:
                        for link, result in zip(self.links, results):
                            link.values.append(result)

                def finalize(self) -> ConstantOutputs:
                    return ConstantOutputs(self.links)

            Outputs = MultiOutputs


        class Function(cls):
            NAME = debug_name

            def run(self, *args: Any, **kwargs: Any) -> ConstantOutputs:
                out = Outputs()

                for values in iter_inputs(self, out):
                    out.add_results(super().run(*values))

                return out.finalize()

        return Function

    return wrapper

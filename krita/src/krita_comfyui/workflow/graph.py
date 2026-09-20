import random
import sys
import math
from typing import Any
from collections.abc import Hashable
from shared import MIN_SEED, MAX_SEED
from shared.graph import Graph
from ..util.krita import Document
from .const import WorkflowError, NodeOutputs, OutputsBase, Link, is_link
from .const import comfyui, krita, selection, basic_data_handling


# The node IDs which can be constant evaluated.
CONST_NODES = {
    **comfyui.CONST_NODES,
    **krita.CONST_NODES,
    **selection.CONST_NODES,
    **basic_data_handling.CONST_NODES,
}


class WorkflowGraph:
    def __init__(self, *, document: Document, json: dict[str, Any], ui_values: dict[str, Any], is_live_mode: bool) -> None:
        self.document = document
        self.json = json
        self.ui_values = ui_values
        self.is_live_mode = is_live_mode

        self.graph: Graph = Graph()

        self.cached_bounds: Any = None
        self.cached_canvas: dict[Hashable, Any] = {}
        self.cached_selection: Any = None
        self.cached_layers: dict[Hashable, Any] = {}
        self.cached_layer_images: dict[Hashable, Any] = {}

        # We only evaluate each node one time and cache its output.
        self.cached_outputs: dict[str, OutputsBase] = {}


    def get_ui_values(self, id: str) -> Any:
        try:
            return self.ui_values[id]
        except KeyError:
            raise WorkflowError(f"UI widget [{id}] not found")


    def bounds(self) -> Any:
        if self.cached_bounds is None:
            self.cached_bounds = self.document.bounds()
        return self.cached_bounds


    def get_cached_canvas(self, crop: Any) -> Any:
        cached_canvas = self.cached_canvas.get(crop, None)

        if cached_canvas is None:
            image = self.document.canvas(crop)

            cached_canvas = (
                image.rgb_view(),
                image.alpha_view(),
            )
            self.cached_canvas[crop] = cached_canvas

        return cached_canvas


    @staticmethod
    def random_seed() -> int:
        return random.randint(MIN_SEED, MAX_SEED)


    # Evaluates the node and returns its output.
    def evaluate_node(self, node_id: str) -> OutputsBase:
        try:
            # If we've evaluated this node before, return the cached outputs.
            outputs = self.cached_outputs[node_id]

        except KeyError:
            node = self.json[node_id]
            name = node["class_type"]

            const_node = CONST_NODES.get(name, None)

            # The node isn't const, so just recursively call evaluate_link on its inputs.
            if const_node is None:
                inputs: dict[str, Any] = {}

                for key, value in node["inputs"].items():
                    inputs[key] = self.evaluate_link(value).to_node(self.graph)

                outputs = NodeOutputs(self.graph.node(name, **inputs))

            # The node is const.
            else:
                outputs = const_node(self, node_id, node).run()

            self.cached_outputs[node_id] = outputs

        return outputs


    def evaluate_link(self, value: Any) -> Link:
        # If it's a node link, then follow the link.
        if is_link(value):
            return self.evaluate_node(value[0]).lookup_index(value[1])
        else:
            return Link([value])


    # Returns a graph which contains a copy of all the old nodes, except
    # constant evaluated nodes have been removed and replaced with their
    # constant outputs.
    def evaluate(self) -> Graph:
        has_output_links: dict[str, bool] = {}

        for node in self.json.values():
            for value in node["inputs"].values():
                if is_link(value):
                    link_id = value[0]
                    has_output_links[link_id] = True

        for id in self.json.keys():
            # We only process nodes that don't have any output links.
            #
            # The node will then recursively process its inputs.
            if not has_output_links.get(id, False):
                self.evaluate_node(id)


        output = self.graph
        self.graph = None  # pyright: ignore[reportAttributeAccessIssue]
        return output

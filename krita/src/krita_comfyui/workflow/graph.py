import random
import sys
import math
from shared import MIN_SEED, MAX_SEED
from shared.graph import Graph
from .const import WorkflowError, NodeOutputs, Link, is_link
from .const import comfyui, krita, selection, basic_data_handling


# The node IDs which can be constant evaluated.
CONST_NODES = {
    **comfyui.CONST_NODES,
    **krita.CONST_NODES,
    **selection.CONST_NODES,
    **basic_data_handling.CONST_NODES,
}


class WorkflowGraph:
    def __init__(self, *, document, json, ui_values, is_live_mode):
        self.document = document
        self.json = json
        self.ui_values = ui_values
        self.is_live_mode = is_live_mode

        self.graph = Graph()

        self.cached_bounds = None
        self.cached_canvas = {}
        self.cached_selection = None
        self.cached_layers = {}
        self.cached_layer_images = {}

        # We only evaluate each node one time and cache its output.
        self.cached_outputs = {}


    def get_ui_values(self, id):
        try:
            return self.ui_values[id]
        except KeyError:
            raise WorkflowError(f"UI widget [{id}] not found")


    def bounds(self):
        if self.cached_bounds is None:
            self.cached_bounds = self.document.bounds()
        return self.cached_bounds


    @staticmethod
    def random_seed():
        return random.randint(MIN_SEED, MAX_SEED)


    # Evaluates the node and returns its output.
    def evaluate_node(self, node_id):
        try:
            # If we've evaluated this node before, return the cached outputs.
            outputs = self.cached_outputs[node_id]

        except KeyError:
            node = self.json[node_id]
            name = node["class_type"]

            const_node = CONST_NODES.get(name, None)

            # The node isn't const, so just recursively call evaluate_link on its inputs.
            if const_node is None:
                inputs = {}

                for key, value in node["inputs"].items():
                    inputs[key] = self.evaluate_link(value).to_node(self.graph)

                outputs = NodeOutputs(self.graph.node(name, **inputs))

            # The node is const.
            else:
                outputs = const_node(self, node_id, node).run()

            self.cached_outputs[node_id] = outputs

        return outputs


    def evaluate_link(self, value):
        # If it's a node link, then follow the link.
        if is_link(value):
            return self.evaluate_node(value[0]).lookup_index(value[1])
        else:
            return Link([value])


    # Returns a graph which contains a copy of all the old nodes, except
    # constant evaluated nodes have been removed and replaced with their
    # constant outputs.
    def evaluate(self):
        has_output_links = {}

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
        self.graph = None
        return output

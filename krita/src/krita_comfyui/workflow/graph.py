import random
import sys
from ..util.graph import Graph
from .const import WorkflowError, Link, comfyui, krita, selection


def is_link(value):
    return isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and isinstance(value[1], int)


class ConstOutputs:
    def __init__(self, outputs):
        self.outputs = outputs

    def out(self, index):
        return self.outputs[index]


class NormalOutputs:
    def __init__(self, node):
        self.node = node

    def out(self, index):
        return Link([self.node.out(index)])


class WorkflowGraph:
    def __init__(self, document, json, seed, ui_values, defaults):
        self.document = document
        self.json = json
        self.seed = seed
        self.ui_values = ui_values
        self.defaults = defaults

        self.graph = Graph()

        self.cached_bounds = None

        # We only evaluate each node one time and cache its output.
        self.cached_outputs = {}

        # The node IDs which can be constant evaluated.
        self.const_nodes = {
            "krita_comfyui: KritaUiBoolean": krita.KritaUi("boolean"),
            "krita_comfyui: KritaUiCombo": krita.KritaUi("combo"),
            "krita_comfyui: KritaUiFloat": krita.KritaUi("float"),
            "krita_comfyui: KritaUiInt": krita.KritaUi("int"),
            "krita_comfyui: KritaUiLayerId": krita.KritaUi("layer_id"),
            "krita_comfyui: KritaUiString": krita.KritaUi("string"),

            "krita_comfyui: KritaCanvas": krita.KritaCanvas(),
            "krita_comfyui: KritaDebug": krita.KritaDebug(),
            "krita_comfyui: KritaLayers": krita.KritaLayers(),
            "krita_comfyui: KritaSeed": krita.KritaSeed(),

            "krita_comfyui: KritaSelection": selection.KritaSelection(),
            "krita_comfyui: KritaSelectionBorder": selection.KritaSelectionBorder(),
            "krita_comfyui: KritaSelectionBounds": selection.KritaSelectionBounds(),
            "krita_comfyui: KritaSelectionFeather": selection.KritaSelectionFeather(),
            "krita_comfyui: KritaSelectionGrow": selection.KritaSelectionGrow(),
            "krita_comfyui: KritaSelectionInvert": selection.KritaSelectionInvert(),
            "krita_comfyui: KritaSelectionMask": selection.KritaSelectionMask(),
            "krita_comfyui: KritaSelectionShrink": selection.KritaSelectionShrink(),
            "krita_comfyui: KritaSelectionSmooth": selection.KritaSelectionSmooth(),

            "PrimitiveString": comfyui.Primitive(),
            "PrimitiveStringMultiline": comfyui.Primitive(),
            "PrimitiveInt": comfyui.Primitive(),
            "PrimitiveFloat": comfyui.Primitive(),
            "PrimitiveBoolean": comfyui.Primitive(),
            "ComfySwitchNode": comfyui.Switch(),
        }


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
        # https://github.com/Comfy-Org/ComfyUI/blob/ed201fff08fbbd3dbcc500b252a9f41e8051c256/nodes.py#L1570
        # https://github.com/Comfy-Org/ComfyUI/blob/ed201fff08fbbd3dbcc500b252a9f41e8051c256/comfy_extras/nodes_primitive.py#L52
        return random.randint(0, sys.maxsize)


    # Evaluates the node and returns its output.
    def evaluate_node(self, node_id):
        try:
            # If we've evaluated this node before, return the cached outputs.
            outputs = self.cached_outputs[node_id]

        except KeyError:
            node = self.json[node_id]
            name = node["class_type"]

            const_node = self.const_nodes.get(name, None)

            # The node isn't const, so just recursively call evaluate_link on its inputs.
            if const_node is None:
                inputs = {}

                for key, value in node["inputs"].items():
                    inputs[key] = self.evaluate_link(value).to_node(self.graph)

                outputs = NormalOutputs(self.graph.node(name, **inputs))

            # The node is const.
            else:
                outputs = ConstOutputs(const_node.get_outputs(self, node_id, node))

            self.cached_outputs[node_id] = outputs

        return outputs


    def evaluate_link(self, value):
        # If it's a node link, then follow the link.
        if is_link(value):
            return self.evaluate_node(value[0]).out(value[1])
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

        return self.graph

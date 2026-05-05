import random
import sys
from ..util.graph import Graph
from .const import WorkflowError, Link, comfyui, krita, selection


def is_link(value):
    return isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and isinstance(value[1], int)


class WorkflowGraph:
    def __init__(self, document, json, seed, ui_values):
        self.document = document
        self.json = json
        self.seed = seed

        self.graph = Graph()

        self.cached_bounds = None

        # The cached depth of each node.
        self.node_depths = {}

        # When we copy an existing node, we have to replace the old node ID with the new node ID.
        self.replaced_ids = {}

        # Cached outputs for constant-evaluated nodes.
        self.const_outputs = {}

        # The node IDs which can be constant evaluated.
        self.const_nodes = {
            "krita_comfyui: KritaUiBoolean": krita.KritaUi(ui_values, "boolean"),
            "krita_comfyui: KritaUiCombo": krita.KritaUi(ui_values, "combo"),
            "krita_comfyui: KritaUiFloat": krita.KritaUi(ui_values, "float"),
            "krita_comfyui: KritaUiInt": krita.KritaUi(ui_values, "int"),
            "krita_comfyui: KritaUiLayerId": krita.KritaUi(ui_values, "layer_id"),
            "krita_comfyui: KritaUiString": krita.KritaUi(ui_values, "string"),

            "krita_comfyui: KritaCanvas": krita.KritaCanvas(),
            "krita_comfyui: KritaDebug": krita.KritaDebug()
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


    def bounds(self):
        if self.cached_bounds is None:
            self.cached_bounds = self.document.bounds()
        return self.cached_bounds


    @staticmethod
    def random_seed():
        # https://github.com/Comfy-Org/ComfyUI/blob/ed201fff08fbbd3dbcc500b252a9f41e8051c256/nodes.py#L1570
        # https://github.com/Comfy-Org/ComfyUI/blob/ed201fff08fbbd3dbcc500b252a9f41e8051c256/comfy_extras/nodes_primitive.py#L52
        return random.randint(0, sys.maxsize)


    # Evaluates the link if the connected node has a constant value.
    def evaluate_link(self, value):
        # If it's a node link, then follow the link.
        if is_link(value):
            node_id = value[0]

            try:
                # If we've evaluated this node before, return the cached outputs.
                outputs = self.const_outputs[node_id]

            # We haven't evaluated this node before.
            except KeyError:
                node = self.json[node_id]
                name = node["class_type"]

                try:
                    const_node = self.const_nodes[name]

                # The node isn't constant, that means it's a link to an old node,
                # so we replace its ID with the new ID.
                except KeyError:
                    # TODO cache this in const_outputs somehow ?
                    new_id = self.replaced_ids[node_id]
                    value = [new_id, value[1]]
                    return Link([value])

                outputs = const_node.get_outputs(self, node_id, node)
                self.const_outputs[node_id] = outputs

            return outputs[value[1]]

        else:
            return Link([value])


    def find_depth(self, node_id):
        try:
            max_depth = self.node_depths[node_id]

        except KeyError:
            max_depth = 0

            node = self.json[node_id]

            for value in node["inputs"].values():
                if is_link(value):
                    link_id = value[0]
                    depth = self.find_depth(link_id)
                    max_depth = max(max_depth, depth + 1)

            self.node_depths[node_id] = max_depth

        return max_depth


    # Returns a graph which contains a copy of all the old nodes, except
    # constant evaluated nodes have been removed and replaced with their
    # constant outputs.
    def evaluate(self):
        copied_nodes = []


        for id, node in self.json.items():
            class_type = node["class_type"]

            # We skip const nodes completely, they're evaluated by `evaluate_link`
            if not class_type in self.const_nodes:
                depth = self.find_depth(id)

                # We create a new node which is the same as the old node.
                new_node = self.graph.node(class_type, **node["inputs"])

                # We only process the copied nodes, any other nodes which are created
                # by constant evaluation (images, lists, etc.) won't be touched.
                copied_nodes.append((depth, new_node.id))

                # We have to replace the old node ID with the new node ID.
                self.replaced_ids[id] = new_node.id


        # We evaluate the deepest nodes first, so that way if a Switch is
        # encountered it can do proper dead code elimination of any
        # branches that aren't taken.
        copied_nodes.sort(key=lambda x: x[0], reverse=True)

        for (depth, name) in [(depth, self.graph.nodes[id]["class_type"]) for (depth, id) in copied_nodes]:
            print(depth, name)


        # For all of the copied nodes, we have to constant-evaluate their
        # inputs.
        #
        # We do this in a second pass because we need to evaluate them in
        # the right order (deepest node first) and also we have to replace
        # the old IDs with new IDs from replaced_ids.
        for _, id in copied_nodes:
            node = self.graph.nodes[id]

            inputs = {}

            for key, value in node["inputs"].items():
                inputs[key] = self.evaluate_link(value).to_node(self.graph)

            node["inputs"] = inputs


        return self.graph

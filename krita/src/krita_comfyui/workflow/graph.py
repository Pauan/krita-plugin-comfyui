import random
import sys
import math
from ..util.graph import Graph
from .const import WorkflowError, Link, is_link, comfyui, krita, selection


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


# The node IDs which can be constant evaluated.
CONST_NODES = {
    "krita_comfyui: KritaUiBoolean": krita.KritaUi("boolean", ["value", "is_default"]),
    "krita_comfyui: KritaUiCombo": krita.KritaUi("combo", ["value", "is_default"]),
    "krita_comfyui: KritaUiFloat": krita.KritaUi("float", ["value", "is_default"]),
    "krita_comfyui: KritaUiInt": krita.KritaUi("int", ["value", "is_default"]),
    "krita_comfyui: KritaUiLayerId": krita.KritaUi("layer_id", ["value", "is_default"]),
    "krita_comfyui: KritaUiString": krita.KritaUi("string", ["value", "is_default"]),

    "krita_comfyui: KritaCanvas": krita.KritaCanvas(),
    "krita_comfyui: KritaLayers": krita.KritaLayers(),
    "krita_comfyui: KritaDebug": krita.KritaDebug(),
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

    "Basic data handling: Boolean And": comfyui.Binary("input1", "input2", lambda x, y: x and y),
    "Basic data handling: Boolean Nand": comfyui.Binary("input1", "input2", lambda x, y: not (x and y)),
    "Basic data handling: Boolean Nor": comfyui.Binary("input1", "input2", lambda x, y: not (x or y)),
    "Basic data handling: Boolean Not": comfyui.Unary("input", lambda x: not x),
    "Basic data handling: Boolean Or": comfyui.Binary("input1", "input2", lambda x, y: x or y),
    "Basic data handling: Boolean Xor": comfyui.Binary("input1", "input2", lambda x, y: x != y),

    "Basic data handling: IntCreate": comfyui.Unary("value", lambda x: int(x, 0)),
    "Basic data handling: IntCreateWithBase": comfyui.Binary("value", "base", lambda x, y: int(x, y)),
    "Basic data handling: IntAdd": comfyui.Binary("int1", "int2", lambda x, y: x + y),
    "Basic data handling: IntSubtract": comfyui.Binary("int1", "int2", lambda x, y: x - y),
    "Basic data handling: IntMultiply": comfyui.Binary("int1", "int2", lambda x, y: x * y),
    "Basic data handling: IntDivide": comfyui.Binary("int1", "int2", lambda x, y: x // y),
    #"Basic data handling: IntDivideSafe":
    "Basic data handling: IntBitCount": comfyui.Unary("int_value", lambda x: x.bit_count()),
    "Basic data handling: IntBitLength": comfyui.Unary("int_value", lambda x: x.bit_length()),
    #"Basic data handling: IntFromBytes":
    "Basic data handling: IntModulus": comfyui.Binary("int1", "int2", lambda x, y: x % y),
    "Basic data handling: IntPower": comfyui.Binary("base", "exponent", lambda x, y: x ** y),
    #"Basic data handling: IntToBytes":

    "Basic data handling: FloatCreate": comfyui.Unary("value", lambda x: float(x)),
    "Basic data handling: FloatAdd": comfyui.Binary("float1", "float2", lambda x, y: x + y),
    "Basic data handling: FloatSubtract": comfyui.Binary("float1", "float2", lambda x, y: x - y),
    "Basic data handling: FloatMultiply": comfyui.Binary("float1", "float2", lambda x, y: x * y),
    "Basic data handling: FloatDivide": comfyui.Binary("float1", "float2", lambda x, y: x / y),
    #"Basic data handling: FloatDivideSafe":
    #"Basic data handling: FloatAsIntegerRatio":
    "Basic data handling: FloatFromHex": comfyui.Unary("hex_value", lambda x: float.fromhex(x)),
    "Basic data handling: FloatHex": comfyui.Unary("float_value", lambda x: x.hex()),
    "Basic data handling: FloatIsInteger": comfyui.Unary("float_value", lambda x: x.is_integer()),
    "Basic data handling: FloatPower": comfyui.Binary("base", "exponent", lambda x, y: x ** y),
    "Basic data handling: FloatRound": comfyui.Binary("float_value", "decimal_places", lambda x, y: round(x, y)),

    "Basic data handling: MathAbs": comfyui.Unary("value", lambda x: abs(float(x))),
    #"Basic data handling: MathAcos":
    #"Basic data handling: MathAsin":
    #"Basic data handling: MathAtan":
    #"Basic data handling: MathAtan2":
    "Basic data handling: MathCeil": comfyui.Unary("value", lambda x: math.ceil(float(x))),
    #"Basic data handling: MathCos":
    "Basic data handling: MathDegrees": comfyui.Unary("radians", lambda x: math.degrees(float(x))),
    "Basic data handling: MathE": comfyui.Constant(math.e),
    "Basic data handling: MathExp": comfyui.Unary("value", lambda x: math.exp(float(x))),
    "Basic data handling: MathFloor": comfyui.Unary("value", lambda x: math.floor(float(x))),
    #"Basic data handling: MathLog":
    "Basic data handling: MathLog10": comfyui.Unary("value", lambda x: math.log10(float(x))),
    "Basic data handling: MathMax": comfyui.Binary("value1", "value2", lambda x, y: max(float(x), float(y))),
    "Basic data handling: MathMin": comfyui.Binary("value1", "value2", lambda x, y: min(float(x), float(y))),
    "Basic data handling: MathPi": comfyui.Constant(math.pi),
    "Basic data handling: MathRadians": comfyui.Unary("degrees", lambda x: math.radians(float(x))),
    #"Basic data handling: MathSin":
    "Basic data handling: MathSqrt": comfyui.Unary("value", lambda x: math.sqrt(float(x))),
    #"Basic data handling: MathTan":

    "Basic data handling: CastToBoolean": comfyui.Unary("input", lambda x: bool(x)),
    "Basic data handling: CastToDict": comfyui.Unary("input", lambda x: dict(x)),
    "Basic data handling: CastToFloat": comfyui.Unary("input", lambda x: float(x)),
    "Basic data handling: CastToInt": comfyui.Unary("input", lambda x: int(x)),
    #"Basic data handling: CastToList": CastToList,
    #"Basic data handling: CastToSet": CastToSet,
    "Basic data handling: CastToString": comfyui.Unary("input", lambda x: str(x)),

    "PrimitiveString": comfyui.Primitive(),
    "PrimitiveStringMultiline": comfyui.Primitive(),
    "PrimitiveInt": comfyui.Primitive(),
    "PrimitiveFloat": comfyui.Primitive(),
    "PrimitiveBoolean": comfyui.Primitive(),
    "ComfySwitchNode": comfyui.Switch(),
    "krita_comfyui: Default": comfyui.Default(),
}


class WorkflowGraph:
    def __init__(self, document, json, seed, ui_values):
        self.document = document
        self.json = json
        self.seed = seed
        self.ui_values = ui_values

        self.graph = Graph()

        self.cached_bounds = None
        self.cached_canvas = None
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

            const_node = CONST_NODES.get(name, None)

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

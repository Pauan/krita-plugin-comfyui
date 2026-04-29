from comfy_api.latest import io
from .nodes import LayerId


class KritaUiFloat(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaUiFloat",
            display_name="Krita UI Float",
            category="krita/ui",
            description="Retrieves a float from Krita.",
            inputs=[
                io.String.Input("id", default="", tooltip="Unique ID of the float."),
            ],
            outputs=[
                io.Float.Output(display_name="float", is_output_list=True),
            ],
        )

    @classmethod
    def execute(cls, id) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaUiInt(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaUiInt",
            display_name="Krita UI Int",
            category="krita/ui",
            description="Retrieves an int from Krita.",
            inputs=[
                io.String.Input("id", default="", tooltip="Unique ID of the int."),
            ],
            outputs=[
                io.Int.Output(display_name="int", is_output_list=True),
            ],
        )

    @classmethod
    def execute(cls, id) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaUiBoolean(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaUiBoolean",
            display_name="Krita UI Boolean",
            category="krita/ui",
            description="Retrieves a boolean from Krita.",
            inputs=[
                io.String.Input("id", default="", tooltip="Unique ID of the checkbox."),
            ],
            outputs=[
                io.Boolean.Output(display_name="boolean", is_output_list=True),
            ],
        )

    @classmethod
    def execute(cls, id) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaUiString(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaUiString",
            display_name="Krita UI String",
            category="krita/ui",
            description="Retrieves a string from Krita.",
            inputs=[
                io.String.Input("id", default="", tooltip="Unique ID of the textbox."),
            ],
            outputs=[
                io.String.Output(display_name="string", is_output_list=True),
            ],
        )

    @classmethod
    def execute(cls, id) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaUiLayerId(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaUiLayerId",
            display_name="Krita UI Layer Id",
            category="krita/ui",
            description="Retrieves a layer ID from Krita.",
            inputs=[
                io.String.Input("id", default="", tooltip="Unique ID of the layer selector."),
            ],
            outputs=[
                LayerId.Output(display_name="layer_id", is_output_list=True),
                io.Boolean.Output(display_name="has_value", is_output_list=True, tooltip="Whether the layer selector has a value."),
            ],
        )

    @classmethod
    def execute(cls, id) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")


class KritaUiCombo(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaUiCombo",
            display_name="Krita UI Combo",
            category="krita/ui",
            description="Retrieves a combo value from Krita.",
            inputs=[
                io.String.Input("id", default="", tooltip="Unique ID of the combo box."),
            ],
            outputs=[
                io.Combo.Output(display_name="combo", is_output_list=True),
                io.Boolean.Output(display_name="has_value", is_output_list=True, tooltip="Whether the combo box has a value."),
            ],
        )

    @classmethod
    def execute(cls, id) -> io.NodeOutput:
        raise RuntimeError("Workflow must be run from Krita.")

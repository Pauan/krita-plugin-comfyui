from comfy_api.latest import io

MIN_INT = -2147483648
MAX_INT = 2147483647

# Krita UI Widget
@io.comfytype(io_type="KRITA_WIDGET")
class KritaWidget(io.ComfyTypeIO):
    pass


class KritaUiFloat(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaUiFloat",
            display_name="Krita UI Float",
            category="krita/ui/widget",
            description="Creates a float UI in Krita and gets its value.",
            inputs=[
                io.String.Input("id", default="float", tooltip="Unique ID of the float."),
                io.String.Input("label", default="Float", tooltip="Label for the widget."),
                io.String.Input("tooltip", default="Float", tooltip="Tooltip for the widget."),
                io.Float.Input("default", default=0.0, step=0.001, round=0.001),
                io.Float.Input("min", default=0.0, step=0.001, round=0.001),
                io.Float.Input("max", default=1.0, step=0.001, round=0.001),
                io.Float.Input("step", default=0.05, step=0.001, round=0.001, tooltip="How much it should increase / decrease when pressing the buttons."),
                io.Combo.Input("mode", default="textbox", options=["textbox", "slider"], tooltip="The type of widget in Krita."),
            ],
            outputs=[
                KritaWidget.Output(display_name="widget"),
                io.Float.Output(display_name="value", is_output_list=True),
            ],
        )

    @classmethod
    def execute(cls, id, label, tooltip, default, min, max, step, mode) -> io.NodeOutput:
        return io.NodeOutput(None, [default])


class KritaUiInt(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaUiInt",
            display_name="Krita UI Int",
            category="krita/ui/widget",
            description="Creates an int UI in Krita and gets its value.",
            inputs=[
                io.String.Input("id", default="int", tooltip="Unique ID of the int."),
                io.String.Input("label", default="Int", tooltip="Label for the widget."),
                io.String.Input("tooltip", default="Int", tooltip="Tooltip for the widget."),
                io.Int.Input("default", default=0),
                io.Int.Input("min", default=MIN_INT),
                io.Int.Input("max", default=MAX_INT),
                io.Int.Input("step", default=1, tooltip="How much it should increase / decrease when pressing the buttons."),
                io.Combo.Input("mode", default="textbox", options=["textbox", "slider"], tooltip="The type of widget in Krita."),
            ],
            outputs=[
                KritaWidget.Output(display_name="widget"),
                io.Int.Output(display_name="value", is_output_list=True),
            ],
        )

    @classmethod
    def execute(cls, id, label, tooltip, default, min, max, step) -> io.NodeOutput:
        return io.NodeOutput(None, [default])


class KritaUiBoolean(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaUiBoolean",
            display_name="Krita UI Boolean",
            category="krita/ui/widget",
            description="Creates a checkbox UI in Krita and gets its value.",
            inputs=[
                io.String.Input("id", default="checkbox", tooltip="Unique ID of the checkbox."),
                io.String.Input("label", default="Enabled", tooltip="Label for the widget."),
                io.String.Input("tooltip", default="Boolean", tooltip="Tooltip for the widget."),
                io.Boolean.Input("default", default=False),
            ],
            outputs=[
                KritaWidget.Output(display_name="widget"),
                io.Boolean.Output(display_name="value", is_output_list=True),
            ],
        )

    @classmethod
    def execute(cls, id, label, tooltip, default) -> io.NodeOutput:
        return io.NodeOutput(None, [default])


class KritaUiString(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaUiString",
            display_name="Krita UI String",
            category="krita/ui/widget",
            description="Creates a textbox UI in Krita and gets its value.",
            inputs=[
                io.String.Input("id", default="textbox", tooltip="Unique ID of the textbox."),
                io.String.Input("label", default="Text", tooltip="Label for the widget."),
                io.String.Input("tooltip", default="Text", tooltip="Tooltip for the widget."),
                io.String.Input("default", default=""),
                io.Boolean.Input("multiline", default=False, tooltip="Whether the textbox should have multiple lines."),
            ],
            outputs=[
                KritaWidget.Output(display_name="widget"),
                io.String.Output(display_name="value", is_output_list=True),
            ],
        )

    @classmethod
    def execute(cls, id, label, tooltip, default, multiline) -> io.NodeOutput:
        return io.NodeOutput(None, [default])


class KritaUiLayer(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaUiLayer",
            display_name="Krita UI Layer",
            category="krita/ui/widget",
            description="Creates a layer selection UI in Krita and gets its value.",
            inputs=[
                io.String.Input("id", default="layer", tooltip="Unique ID of the layer selector."),
                io.String.Input("label", default="Layer", tooltip="Label for the widget."),
                io.String.Input("tooltip", default="Layer", tooltip="Tooltip for the widget."),
            ],
            outputs=[
                KritaWidget.Output(display_name="widget"),
                io.String.Output(display_name="value", is_output_list=True),
            ],
        )

    @classmethod
    def execute(cls, id, label, tooltip, default) -> io.NodeOutput:
        return io.NodeOutput(None, [])


class KritaUiCombo(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: KritaUiCombo",
            display_name="Krita UI Combo",
            category="krita/ui/widget",
            description="Creates a combo box UI in Krita and gets its value.",
            inputs=[
                io.String.Input("id", default="combo box", tooltip="Unique ID of the combo box."),
                io.String.Input("label", default="Combo", tooltip="Label for the widget."),
                io.String.Input("tooltip", default="Combo", tooltip="Tooltip for the widget."),
                io.String.Input("default", default=""),
            ],
            outputs=[
                KritaWidget.Output(display_name="widget"),
                io.Combo.Output(display_name="value", is_output_list=True),
            ],
        )

    @classmethod
    def execute(cls, id, label, tooltip, default) -> io.NodeOutput:
        return io.NodeOutput(None, [default])


class KritaUiList(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        template = io.Autogrow.TemplatePrefix(input=KritaWidget.Input("widget"), prefix="widget", min=1, max=100)
        return io.Schema(
            node_id="krita_comfyui: KritaUiList",
            display_name="Krita UI List",
            category="krita/ui",
            description="Creates a list of widgets which can be dynamically added and removed.",
            inputs=[
                io.String.Input("id", default="list", tooltip="Unique ID of the list."),
                io.String.Input("label", default="List", tooltip="Label for the list."),
                io.String.Input("tooltip", default="List", tooltip="Tooltip for the list."),
                io.Autogrow.Input("widgets", template=template),
            ],
            outputs=[
                KritaWidget.Output(display_name="widget"),
            ],
        )

    @classmethod
    def execute(cls, id, label, tooltip, widgets) -> io.NodeOutput:
        return io.NodeOutput(None)


class KritaUiGroup(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        template = io.Autogrow.TemplatePrefix(input=KritaWidget.Input("widget"), prefix="widget", min=1, max=100)
        return io.Schema(
            node_id="krita_comfyui: KritaUiGroup",
            display_name="Krita UI Group",
            category="krita/ui",
            description="Combines multiple widgets into a collapsible group.",
            inputs=[
                io.String.Input("id", default="group", tooltip="Unique ID of the group."),
                io.String.Input("label", default="Group", tooltip="Label for the group."),
                io.String.Input("tooltip", default="Group", tooltip="Tooltip for the group."),
                io.Autogrow.Input("widgets", template=template),
            ],
            outputs=[
                KritaWidget.Output(display_name="widget"),
            ],
        )

    @classmethod
    def execute(cls, id, label, tooltip, widgets) -> io.NodeOutput:
        return io.NodeOutput(None)


class KritaUiRow(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        template = io.Autogrow.TemplatePrefix(input=KritaWidget.Input("widget"), prefix="widget", min=1, max=100)
        return io.Schema(
            node_id="krita_comfyui: KritaUiRow",
            display_name="Krita UI Row",
            category="krita/ui",
            description="Combines multiple widgets into a single row.",
            inputs=[
                io.Autogrow.Input("widgets", template=template),
            ],
            outputs=[
                KritaWidget.Output(display_name="widget"),
            ],
        )

    @classmethod
    def execute(cls, widgets) -> io.NodeOutput:
        return io.NodeOutput(None)


class KritaUiRoot(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        template = io.Autogrow.TemplatePrefix(input=KritaWidget.Input("widget"), prefix="widget", min=1, max=100)
        return io.Schema(
            node_id="krita_comfyui: KritaUiRoot",
            display_name="Krita UI Root",
            category="krita/ui",
            description="All UI widgets must be connected to the root.",
            inputs=[
                io.String.Input("name", default="Custom", tooltip="Name for the workflow in Krita."),
                io.String.Input("icon", default="bookmarks", tooltip="Krita icon for the workflow. You can find the available icons here:\n\nhttps://scripting.krita.org/icon-library"),
                io.Autogrow.Input("widgets", template=template),
            ],
            outputs=[],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, name, icon, widgets) -> io.NodeOutput:
        return io.NodeOutput()

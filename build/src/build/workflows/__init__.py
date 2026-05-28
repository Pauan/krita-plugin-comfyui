import json
from pathlib import Path
from shared.graph import Graph

class Workflow:
    def __init__(self, root):
        self.folder = root / "krita" / "src" / "krita_comfyui" / "settings" / "defaults" / "workflows"
        self.graph = Graph()


    def write(self):
        self.make_graph()

        with open(self.folder / self.FILENAME, "r") as file:
            workflow = json.load(file)
            workflow["graph"] =  self.graph.finalize()

            with open(self.folder / self.FILENAME, "w") as file:
                json.dump(workflow, file, indent=2)


    def krita_ui_combo(self, id):
        return self.graph.node("krita_comfyui: KritaUiCombo", id=id)


    def krita_ui_int(self, id):
        return self.graph.node("krita_comfyui: KritaUiInt", id=id)


    def krita_ui_boolean(self, id):
        return self.graph.node("krita_comfyui: KritaUiBoolean", id=id)


    def krita_canvas(self, crop=None):
        if crop is None:
            return self.graph.node("krita_comfyui: KritaCanvasImage")
        else:
            return self.graph.node("krita_comfyui: KritaCanvasImage", crop=crop)


    def krita_output(self, *, images, name, order, x, y, canvas_resize, resize_other_layers, resize_algorithm):
        return self.graph.node("krita_comfyui: KritaOutput",
            images=images,
            name=name,
            order=order,
            x=x,
            y=y,
            canvas_resize=canvas_resize,
            resize_other_layers=resize_other_layers,
            resize_algorithm=resize_algorithm,
        )


    def math_expression(self, expression, values):
        inputs = {
            "expression": expression,
        }

        for key, value in values.items():
            inputs[f"values.{key}"] = value

        return self.graph.node("ComfyMathExpression", **inputs)


    def resize_image_mask(self, *, input, width, height, scale_method):
        inputs = {
            "input": input,
            "resize_type": "scale dimensions",
            "resize_type.width": width,
            "resize_type.height": height,
            "resize_type.crop": "disabled",
            "scale_method": scale_method,
        }
        return self.graph.node("ResizeImageMaskNode", **inputs)

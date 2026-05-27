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


class Anima(Workflow):
    FILENAME = "f4516100-d999-4d82-8ecd-50dd545bc1fe.json"

    def make_graph(self):
        pass


class Upscale(Workflow):
    FILENAME = "6b904c3a-0d4b-43d1-86d7-0474dcb8bf2d.json"

    def make_graph(self):
        model = self.krita_ui_combo("model")
        scale_method = self.krita_ui_combo("scale_method")
        multiplier = self.krita_ui_int("multiplier")
        resize_layers = self.krita_ui_boolean("resize_layers")
        resize_layers_algorithm = self.krita_ui_combo("resize_layers_algorithm")
        canvas = self.krita_canvas()

        split_image = self.graph.node("SplitImageWithAlpha", image=canvas.out(0))

        load_upscale_model = self.graph.node("UpscaleModelLoader", model_name=model.out(0))

        upscale_image = self.graph.node("ImageUpscaleWithModel",
            upscale_model=load_upscale_model.out(0),
            image=split_image.out(0),
        )

        image_size = self.graph.node("GetImageSize", image=canvas.out(0))

        width = self.math_expression("a * b", {
            "a": image_size.out(0),
            "b": multiplier.out(0),
        })

        height = self.math_expression("a * b", {
            "a": image_size.out(1),
            "b": multiplier.out(0),
        })

        resize_image = self.resize_image_mask(
            input=upscale_image.out(0),
            scale_method=scale_method.out(0),
            width=width.out(1),
            height=height.out(1),
        )

        resize_mask = self.resize_image_mask(
            input=canvas.out(1),
            scale_method=scale_method.out(0),
            width=width.out(1),
            height=height.out(1),
        )

        add_alpha = self.graph.node("krita_comfyui: AddAlphaToImage", image=resize_image.out(0), alpha=resize_mask.out(0))

        name = self.graph.node("RegexReplace",
            string=model.out(1),
            regex_pattern=r"\.[^\.]+$",
            replace="",
            case_insensitive=False,
            multiline=False,
            dotall=False,
            count=0,
        )

        self.krita_output(
            images=add_alpha.out(0),
            name=name.out(0),
            order=0,
            x=0,
            y=0,
            canvas_resize="enlarge",
            resize_other_layers=resize_layers.out(0),
            resize_algorithm=resize_layers_algorithm.out(0),
        )

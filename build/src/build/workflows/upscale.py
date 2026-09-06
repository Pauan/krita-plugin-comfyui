from . import Workflow

class Upscale(Workflow):
    FILENAME = "6b904c3a-0d4b-43d1-86d7-0474dcb8bf2d.json"


    def name(self, model):
        return self.graph.node("RegexReplace",
            string=model.out(1),
            regex_pattern=r"\.[^\.]+$",
            replace="",
            case_insensitive=False,
            multiline=False,
            dotall=False,
            count=0,
        ).out(0)


    def upscale_image(self, model):
        multiplier = self.krita_ui_int("multiplier")
        scale_method = self.krita_ui_combo("scale_method")
        canvas = self.krita_canvas()

        load_upscale_model = self.graph.node("UpscaleModelLoader", model_name=model.out(0))

        upscale_image = self.graph.node("ImageUpscaleWithModel",
            upscale_model=load_upscale_model.out(0),
            image=canvas.out(0),
        )

        canvas_size = self.graph.node("krita_comfyui: KritaCanvasSize")

        width = self.math_expression("a * b", {
            "a": canvas_size.out(0),
            "b": multiplier.out(0),
        })

        height = self.math_expression("a * b", {
            "a": canvas_size.out(1),
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

        return add_alpha.out(0)


    def make_graph(self):
        model = self.krita_ui_combo("model")
        resize_layers = self.krita_ui_boolean("resize_layers")
        resize_layers_algorithm = self.krita_ui_combo("resize_layers_algorithm")

        image = self.upscale_image(model)

        name = self.name(model)

        self.krita_output(
            images=image,
            name=name,
            order=0,
            x=0,
            y=0,
            batch_mode="separate images",
            canvas_resize="enlarge",
            resize_other_layers=resize_layers.out(0),
            resize_algorithm=resize_layers_algorithm.out(0),
        )

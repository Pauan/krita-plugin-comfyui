from comfy.cldm.control_types import UNION_CONTROLNET_TYPES
from comfy_api.latest import io
from comfy_execution.graph_utils import GraphBuilder


@io.comfytype(io_type="KRITA_CONTROL_NET")
class ControlNet(io.ComfyTypeIO):
    Type = dict


class EmptyControlNet(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: EmptyControlNet",
            display_name="Empty Control Net",
            category="conditioning/controlnet",
            description="Makes an empty control net that does nothing.",
            inputs=[],
            outputs=[
                ControlNet.Output(display_name="control_net"),
            ],
        )

    @classmethod
    def execute(cls) -> io.NodeOutput:
        return io.NodeOutput(None)


class MakeControlNet(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: MakeControlNet",
            display_name="Make Control Net",
            category="conditioning/controlnet",
            description="Makes a control net.",
            inputs=[
                io.Image.Input("image"),

                io.ControlNet.Input("model"),

                # https://github.com/Comfy-Org/ComfyUI/blob/dabfe73dc0e954554fe9632216149964bb9b295f/comfy_extras/nodes_controlnet.py#L15
                io.Combo.Input("type", default="auto", options=["auto"] + list(UNION_CONTROLNET_TYPES.keys())),

                # https://github.com/Comfy-Org/ComfyUI/blob/dabfe73dc0e954554fe9632216149964bb9b295f/nodes.py#L888-L890
                io.Float.Input("strength", default=1.0, min=0.0, max=10.0, step=0.01),
                io.Float.Input("start_percent", default=0.0, min=0.0, max=1.0, step=0.001),
                io.Float.Input("end_percent", default=1.0, min=0.0, max=1.0, step=0.001),
            ],
            outputs=[
                ControlNet.Output(display_name="control_net"),
            ],
        )

    @classmethod
    def execute(cls, image, model, type, strength, start_percent, end_percent) -> io.NodeOutput:
        return io.NodeOutput({
            "image": image,
            "model": model,
            "type": type,
            "strength": strength,
            "start_percent": start_percent,
            "end_percent": end_percent,
        })


class ApplyControlNets(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: ApplyControlNets",
            display_name="Apply Control Nets",
            category="conditioning/controlnet",
            description="Applies the control nets.",
            inputs=[
                io.Conditioning.Input("positive"),
                io.Conditioning.Input("negative"),
                io.Vae.Input("vae"),
                ControlNet.Input("control_nets", optional=True),
            ],
            outputs=[
                io.Conditioning.Output(display_name="positive"),
                io.Conditioning.Output(display_name="negative"),
                io.Image.Output(display_name="images", is_output_list=True),
            ],
            is_input_list=True,
            enable_expand=True,
        )

    @classmethod
    def execute(cls, positive, negative, vae, control_nets=[]) -> io.NodeOutput:
        assert len(positive) == 1
        assert len(negative) == 1
        assert len(vae) == 1

        positive = positive[0]
        negative = negative[0]
        vae = vae[0]

        graph = GraphBuilder()

        images = []

        for control_net in control_nets:
            if control_net is not None:
                model = control_net["model"]
                print(model.get_extra_arg("control_type"))

                model = graph.node("SetUnionControlNetType", control_net=model, type=control_net["type"]).out(0)

                image = control_net["image"]

                match control_net["type"]:
                    case "hed/pidi/scribble/ted" | "canny/lineart/anime_lineart/mlsd":
                        size = graph.node("GetImageSize", image=image)

                        empty_image = graph.node("EmptyImage",
                            width=size.out(0),
                            height=size.out(1),
                            batch_size=size.out(2),
                            # Pure white
                            color=0xFFFFFF,
                        ).out(0)

                        image = graph.node("ImageCompositeMasked",
                            destination=empty_image,
                            source=image,
                            mask=None,
                            x=0,
                            y=0,
                            resize_source=False,
                        ).out(0)

                        image = graph.node("ImageInvert", image=image).out(0)

                images.append(image)

                apply = graph.node("ControlNetApplyAdvanced",
                    positive=positive,
                    negative=negative,
                    control_net=model,
                    image=image,
                    vae=vae,
                    strength=control_net["strength"],
                    start_percent=control_net["start_percent"],
                    end_percent=control_net["end_percent"],
                )

                positive = apply.out(0)
                negative = apply.out(1)

        return io.NodeOutput(positive, negative, images, expand=graph.finalize())

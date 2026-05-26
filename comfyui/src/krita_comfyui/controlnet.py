import folder_paths
from comfy.cldm.control_types import UNION_CONTROLNET_TYPES
from comfy_api.latest import io
from comfy_execution.graph_utils import GraphBuilder
from .shared import zip_lists


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
                io.Mask.Input("mask", tooltip="Mask which is used for inpainting control nets. The white parts of the mask will be inpainted.", optional=True),

                # https://github.com/Comfy-Org/ComfyUI/blob/c9589f29b21fc5f73b6eb9d5c98d29a68cf8c392/nodes.py#L818
                io.Combo.Input("model", options=folder_paths.get_filename_list("controlnet")),

                io.DynamicCombo.Input("type", options=[
                    io.DynamicCombo.Option("Anima LLLite", []),
                    io.DynamicCombo.Option("Union", [
                        # https://github.com/Comfy-Org/ComfyUI/blob/dabfe73dc0e954554fe9632216149964bb9b295f/comfy_extras/nodes_controlnet.py#L15
                        io.Combo.Input("union_type", default="auto", options=["auto"] + list(UNION_CONTROLNET_TYPES.keys())),
                    ]),
                ]),

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
    def execute(cls, image, model, type, strength, start_percent, end_percent, mask=None) -> io.NodeOutput:
        return io.NodeOutput({
            "image": image,
            "mask": mask,
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
                io.Model.Input("model"),
                io.Conditioning.Input("positive"),
                io.Conditioning.Input("negative"),
                io.Vae.Input("vae"),
                ControlNet.Input("control_nets", optional=True),
            ],
            outputs=[
                io.Model.Output(display_name="model", is_output_list=True),
                io.Conditioning.Output(display_name="positive", is_output_list=True),
                io.Conditioning.Output(display_name="negative", is_output_list=True),
                io.Image.Output(display_name="images", is_output_list=True, tooltip="The final control net images, useful for debugging."),
            ],
            is_input_list=True,
            enable_expand=True,
        )


    @staticmethod
    def anima(graph, model, control_net, image):
        return graph.node("AnimaLLLiteApply",
            model=model,
            lllite_name=control_net["model"],
            image=image,
            mask=control_net["mask"],
            strength=control_net["strength"],
            start_percent=control_net["start_percent"],
            end_percent=control_net["end_percent"],
        ).out(0)


    @staticmethod
    def union(graph, positive, negative, vae, control_net, image):
        model = graph.node("ControlNetLoader", control_net_name=control_net["model"]).out(0)
        model = graph.node("SetUnionControlNetType", control_net=model, type=control_net["type"]["union_type"]).out(0)

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
        return (positive, negative)


    @classmethod
    def execute(cls, model, positive, negative, vae, control_nets=[]) -> io.NodeOutput:
        graph = GraphBuilder()

        models = []
        positives = []
        negatives = []
        images = []

        for model, positive, negative, vae in zip_lists([model, positive, negative, vae]):
            for control_net in control_nets:
                if (
                    control_net is not None and
                    control_net["strength"] > 0.0 and
                    control_net["start_percent"] < control_net["end_percent"]
                ):
                    image = control_net["image"]
                    images.append(image)

                    match control_net["type"]["type"]:
                        case "Anima LLLite":
                            model = cls.anima(graph, model, control_net, image)

                        case "Union":
                            (positive, negative) = cls.union(graph, positive, negative, vae, control_net, image)

                        case x:
                            raise RuntimeError(f"Unknown type {x}")

            models.append(model)
            positives.append(positive)
            negatives.append(negative)

        return io.NodeOutput(models, positives, negatives, images, expand=graph.finalize())

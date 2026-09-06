import torch
from comfy_api.latest import io
from comfy_execution.graph_utils import GraphBuilder
from shared.graph import graph_list
from .util import mask_bounds, mask_inverse_sum
from .region_attention import AttentionMaskPatch


@io.comfytype(io_type="KRITA_REGION")
class Region(io.ComfyTypeIO):
    Type = dict


class RegionMask(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: RegionMask",
            display_name="Region Mask",
            category="krita/region",
            description="Creates a region with a mask.",
            inputs=[
                io.Mask.Input("mask", optional=True, tooltip="Mask for the region."),
                io.String.Input("name", optional=True, default="", tooltip="Name for the region. Used for debugging."),
                io.String.Input("prompt", multiline=True, tooltip="Prompt that will be applied only within the region."),
                io.Float.Input("strength", default=1.0, min=0.0, max=10.0, step=0.01, round=0.01, advanced=True),
                io.Boolean.Input("isolated", default=False, tooltip="If this is true then the prompt is isolated inside the mask.\n\nIf this is false then the prompt is blended with the rest of the image outside of the mask.", advanced=True),
                io.Boolean.Input("add_to_global", default=True, tooltip="If this is true then the prompt is automatically added to the global prompt.", advanced=True),
            ],
            outputs=[
                Region.Output(display_name="region"),
            ],
        )

    @classmethod
    def execute(cls, name, prompt, strength, add_to_global, isolated, mask=None) -> io.NodeOutput:
        if mask is not None:
            #if mask.dim() < 3:
                #mask = mask.unsqueeze(0)

            if strength < 1.0:
                mask = torch.clamp(mask * strength, 0.0, 1.0)

        return io.NodeOutput({
            "name": name,
            "prompt": prompt,
            "mask": mask,
            "strength": strength,
            "add_to_global": add_to_global,
            "isolated": isolated,
        })


class RegionSubtract(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: RegionSubtract",
            display_name="Region: Subtract",
            category="krita/region",
            description="Subtracts the regions from this region.\n\nThis is useful to create a background region for everything outside of the regions.",
            inputs=[
                Region.Input("region"),
                Region.Input("regions"),
            ],
            outputs=[
                Region.Output(display_name="region", is_output_list=True),
            ],
            is_input_list=True,
            enable_expand=True,
        )

    @classmethod
    def execute(cls, region, regions) -> io.NodeOutput:
        graph = GraphBuilder()

        outputs = []

        for region in region:
            mask = region["mask"]

            for regions in regions:
                mask = graph.node("MaskComposite",
                    destination=mask,
                    source=regions["mask"],
                    x=0,
                    y=0,
                    operation="subtract",
                ).out(0)

            region = region.copy()
            region["mask"] = mask
            outputs.append(region)

        return io.NodeOutput(outputs, expand=graph.finalize())


class RegionsDebug(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: RegionsDebug",
            display_name="Regions Debug",
            category="krita/region",
            description="Debugs the regions.",
            inputs=[
                Region.Input("regions", optional=True),
            ],
            outputs=[
                io.String.Output(is_output_list=True, display_name="prompts"),
                io.Mask.Output(is_output_list=True, display_name="masks"),
                io.Mask.Output(display_name="inverse_mask"),
            ],
            is_input_list=True,
        )

    @classmethod
    def execute(cls, regions=[]) -> io.NodeOutput:
        prompts = []
        masks = []

        for region in regions:
            if region["strength"] > 0.0:
                prompts.append(region["prompt"])
                masks.append(region["mask"])

        if len(masks) == 0:
            masks.append(torch.full((1, 8, 8), 0.0, dtype=torch.float32))

        return io.NodeOutput(prompts, masks, mask_inverse_sum(masks))


class RegionsEncodeState:
    def __init__(self, clip, combine_prompts):
        self.graph = GraphBuilder()
        self.prompt_cache = {}
        self.clip = clip
        self.combine_method = combine_prompts


    def encode_prompt(self, prompt):
        encoded = self.prompt_cache.get(prompt, None)

        if encoded is None:
            encoded = self.graph.node("CLIPTextEncode", clip=self.clip, text=prompt).out(0)
            self.prompt_cache[prompt] = encoded

        return encoded


    def combine_prompts(self, prompts):
        if self.combine_method == "String Concatenate":
            return self.encode_prompt("\n".join(prompts))

        elif self.combine_method == "Conditioning (Concat)":
            combined = None

            for prompt in prompts:
                encoded = self.encode_prompt(prompt)

                if combined is None:
                    combined = encoded
                else:
                    combined = self.graph.node("ConditioningConcat", conditioning_to=combined, conditioning_from=encoded).out(0)

            return combined

        elif self.combine_method == "Conditioning (Combine)":
            return self.combine_conditionings([self.encode_prompt(prompt) for prompt in prompts])


    def combine_conditionings(self, conditionings):
        output = None

        for conditioning in conditionings:
            if output is None:
                output = conditioning
            else:
                output = self.graph.node("ConditioningCombine", conditioning_1=output, conditioning_2=conditioning).out(0)

        return output


    def set_mask(self, conditioning, mask, strength):
        return self.graph.node("ConditioningSetMask",
            conditioning=conditioning,
            mask=mask,
            strength=strength,
            set_cond_area="default",
        ).out(0)


    def set_area(self, conditioning, x, y, width, height, strength):
        return self.graph.node("ConditioningSetArea",
            conditioning=conditioning,
            x=x,
            y=y,
            width=width,
            height=height,
            strength=strength,
        ).out(0)


    def set_strength(self, conditioning, strength):
        if strength == 1.0:
            return conditioning
        else:
            return self.graph.node("ConditioningSetAreaStrength", conditioning=conditioning, strength=strength).out(0)


    def set_mask_bounds(self, conditioning, mask, strength):
        (x, y, width, height) = mask_bounds(mask)
        return self.set_area(conditioning, x, y, width, height, strength)


class RegionsEncode(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: RegionsEncode",
            display_name="CLIP Regions Encode",
            category="krita/region",
            description="Encodes the regions into a conditioning.",
            inputs=[
                io.Clip.Input("clip"),
                Region.Input("regions", optional=True),
                io.String.Input("global_prompt", multiline=True, default="", tooltip="Prompt for the entire image."),

                io.Float.Input("global_strength",
                    default=0.01,
                    min=0.0,
                    max=10.0,
                    step=0.01,
                    round=0.01,
                    advanced=True,
                    tooltip="The strength of the global prompt which is applied to the entire image.",
                ),

                io.Float.Input("global_inverse_strength",
                    default=0.0,
                    min=0.0,
                    max=10.0,
                    step=0.01,
                    round=0.01,
                    advanced=True,
                    tooltip="If greater than 0, then the global prompt will be applied to the inverse of the region masks.",
                ),

                io.Boolean.Input("add_to_regions", default=True, advanced=True, tooltip="If true, then the global prompt will be added to all of the region prompts."),

                io.Combo.Input("combine_prompts",
                    default="String Concatenate",
                    options=["String Concatenate", "Conditioning (Concat)", "Conditioning (Combine)"],
                    tooltip="How the prompts will be combined together.",
                    advanced=True,
                ),
            ],
            outputs=[
                io.Conditioning.Output(),

                io.String.Output(
                    display_name="names",
                    is_output_list=True,
                ),

                io.String.Output(
                    display_name="prompts",
                    is_output_list=True,
                ),
            ],
            is_input_list=True,
            enable_expand=True,
        )

    @classmethod
    def execute(cls, clip, global_strength, global_inverse_strength, global_prompt, add_to_regions, combine_prompts, regions=[]) -> io.NodeOutput:
        assert len(clip) == 1
        assert len(global_prompt) == 1
        assert len(global_strength) == 1
        assert len(global_inverse_strength) == 1
        assert len(combine_prompts) == 1
        assert len(add_to_regions) == 1

        clip = clip[0]
        global_prompt = global_prompt[0].strip()
        global_strength = global_strength[0]
        global_inverse_strength = global_inverse_strength[0]
        combine_prompts = combine_prompts[0]
        add_to_regions = add_to_regions[0]

        state = RegionsEncodeState(clip, combine_prompts)

        def should_keep_region(region):
            if region["strength"] > 0.0 and region["mask"] is not None:
                prompt = region["prompt"].strip()
                return prompt != "" and prompt != global_prompt and torch.count_nonzero(region["mask"]).item() > 0
            else:
                return False

        regions = [region for region in regions if should_keep_region(region)]
        outputs = []

        if len(regions) == 0:
            outputs.append(state.encode_prompt(global_prompt))

        else:
            if global_strength > 0.0:
                # Combines the add_to_global prompts with the global_prompt
                prompts = [global_prompt] + [region["prompt"] for region in regions if region["add_to_global"]]
                conditioning = state.combine_prompts(prompts)
                conditioning = state.set_strength(conditioning, global_strength)
                outputs.append(conditioning)


            for region in regions:
                prompt = region["prompt"]
                mask = region["mask"]
                strength = region["strength"]

                if add_to_regions:
                    # We combine the global_prompt with the region's prompt.
                    # If we don't do this then the global_prompt will have a
                    # weak effect inside the region.
                    conditioning = state.combine_prompts([global_prompt, prompt])
                else:
                    conditioning = state.encode_prompt(prompt)

                conditioning = state.set_mask(conditioning, mask, strength)

                if region["isolated"]:
                    conditioning = state.set_mask_bounds(conditioning, mask, strength)

                #conditioning = state.set_strength(conditioning, strength)

                outputs.append(conditioning)


            if global_inverse_strength > 0.0:
                masks = [region["mask"] for region in regions]

                inverse_mask = mask_inverse_sum(masks)

                if torch.any(inverse_mask).item():
                    conditioning = state.encode_prompt(global_prompt)
                    conditioning = state.set_mask(conditioning, inverse_mask, global_inverse_strength)
                    #conditioning = state.set_mask_bounds(conditioning, inverse_mask, global_inverse_strength)
                    #conditioning = state.set_strength(conditioning, global_inverse_strength)
                    outputs.append(conditioning)


        output = state.combine_conditionings(outputs)
        assert output is not None
        return io.NodeOutput(
            output,
            [region["name"] for region in regions],
            [region["prompt"] for region in regions],
            expand=state.graph.finalize(),
        )


class ApplyRegions(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: ApplyRegions",
            display_name="Apply Regions to Model",
            category="krita/region",
            description="Encodes the regions into a conditioning.",
            inputs=[
                io.Model.Input("model"),
                io.Clip.Input("clip"),
                Region.Input("regions", optional=True),
                io.String.Input("global_prompt", multiline=True, default="", tooltip="Prompt for the entire image."),

                io.Float.Input("global_strength", default=0.01, min=0.0, max=10.0, step=0.01, round=0.01, advanced=True),

                io.Boolean.Input("global_inverse", default=False, advanced=True, tooltip="If true, then the global prompt will be applied in the inverse of the region masks."),

                io.Combo.Input("combine_prompts",
                    default="String Concatenate",
                    options=["String Concatenate", "Conditioning (Concat)", "Conditioning (Combine)"],
                    tooltip="How the prompts will be combined together.",
                    advanced=True,
                ),
            ],
            outputs=[
                io.Model.Output(),
                io.Conditioning.Output(),
            ],
            is_input_list=True,
            enable_expand=True,
        )

    @classmethod
    def execute(cls, model, clip, global_inverse, combine_prompts, global_strength, global_prompt, regions=[]) -> io.NodeOutput:
        assert len(model) == 1
        assert len(clip) == 1
        assert len(global_prompt) == 1
        assert len(global_strength) == 1
        assert len(global_inverse) == 1
        assert len(combine_prompts) == 1

        model = model[0]
        clip = clip[0]
        global_prompt = global_prompt[0]
        global_strength = global_strength[0]
        global_inverse = global_inverse[0]
        combine_prompts = combine_prompts[0]

        state = RegionsEncodeState(clip, combine_prompts)

        regions = [region for region in regions if region["strength"] > 0.0 and region["prompt"].strip() != ""]

        if len(regions) == 0:
            output = state.encode_prompt(global_prompt)

        else:
            output = None

            if global_strength > 0.0:
                # Combines the add_to_global prompts with the global_prompt
                prompts = [global_prompt] + [region["prompt"] for region in regions if region["add_to_global"]]

                if global_inverse:
                    mask = mask_inverse_sum([region["mask"] for region in regions])

                    if torch.any(mask).item():
                        output = state.combine_prompts(prompts)
                        output = state.set_mask(output, mask, global_strength)

                else:
                    output = state.combine_prompts(prompts)
                    output = state.set_strength(output, global_strength)


            if output is None:
                output = state.encode_prompt("")
                output = state.set_strength(output, global_strength)

            prompts = [state.set_strength(state.encode_prompt(region["prompt"]), region["strength"]) for region in regions]

            masks = [region["mask"] for region in regions]

            inverse_mask = mask_inverse_sum(masks)

            if torch.any(inverse_mask).item():
                background = state.encode_prompt(global_prompt)
                prompts = [background] + prompts
                masks = [inverse_mask] + masks

            model = state.graph.node("krita_comfyui: ApplyAttentionMasks",
                model=model,
                conditionings=graph_list(state.graph, prompts),
                masks=graph_list(state.graph, masks),
            ).out(0)


        assert output is not None
        return io.NodeOutput(model, output, expand=state.graph.finalize())


class ApplyAttentionMasks(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="krita_comfyui: ApplyAttentionMasks",
            display_name="Apply Attention Masks",
            category="krita/region",
            description="Applies attention masks to the model.",
            inputs=[
                io.Model.Input("model"),
                io.Conditioning.Input("conditionings"),
                io.Mask.Input("masks"),
            ],
            outputs=[
                io.Model.Output(is_output_list=True),
            ],
            is_input_list=True,
        )

    @classmethod
    def execute(cls, model, conditionings, masks) -> io.NodeOutput:
        model = [AttentionMaskPatch(conditionings, masks).apply(model) for model in model]
        return io.NodeOutput(model)

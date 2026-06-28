import sys
from pathlib import Path

# Enables Python to load dependencies
sys.path.append(str(Path(__file__).parent / "site-packages"))


from comfy_api.latest import ComfyExtension, io

from . import controlnet, nodes, ui, region_comfyui


class KritaComfyui(ComfyExtension):
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            # util
            nodes.CombineConditionings,
            nodes.LoadImageBase64,
            nodes.LoadMaskBase64,
            nodes.ThrowError,

            # logic
            nodes.MakeList,
            nodes.Default,

            # latent
            nodes.Img2img,

            # conditioning
            nodes.ClipSkip,

            # conditioning/controlnet
            controlnet.EmptyControlNet,
            controlnet.MakeControlNet,
            controlnet.ApplyControlNets,

            # transform
            nodes.DetailSize,

            # image
            nodes.AddAlphaToImage,
            nodes.ReplaceTransparency,

            # krita/input
            nodes.KritaAnimationFrames,
            nodes.KritaCanvasImage,
            nodes.KritaCanvasSize,
            nodes.KritaLayers,
            nodes.KritaLiveMode,
            nodes.KritaSeed,

            # krita/output
            nodes.KritaDebug,
            nodes.KritaOutput,
            nodes.KritaText,

            # krita/region
            region_comfyui.RegionMask,
            region_comfyui.RegionSubtract,
            region_comfyui.RegionsEncode,
            region_comfyui.RegionsDebug,
            #region_comfyui.ApplyAttentionMasks,

            # krita/selection
            nodes.KritaSelection,
            nodes.KritaSelectionBorder,
            nodes.KritaSelectionBounds,
            nodes.KritaSelectionFeather,
            nodes.KritaSelectionGrow,
            nodes.KritaSelectionInvert,
            nodes.KritaSelectionMask,
            nodes.KritaSelectionShrink,
            nodes.KritaSelectionSmooth,

            # krita/ui
            ui.KritaUiBoolean,
            ui.KritaUiCombo,
            ui.KritaUiFloat,
            ui.KritaUiInt,
            ui.KritaUiLayerId,
            ui.KritaUiPrompt,
            ui.KritaUiString,

            # krita/util
            nodes.ApplyLoras,
        ]

async def comfy_entrypoint() -> KritaComfyui:
    return KritaComfyui()


__all__ = [
    "comfy_entrypoint",
]

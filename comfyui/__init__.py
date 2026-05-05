from comfy_api.latest import ComfyExtension, io

from .src.krita_comfyui import nodes, ui


class KritaComfyui(ComfyExtension):
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            # util
            nodes.LoadImageBase64,
            nodes.LoadMaskBase64,
            nodes.ThrowError,

            # krita
            nodes.KritaCanvas,
            nodes.KritaLayers,
            nodes.KritaOutput,
            nodes.KritaSeed,
            nodes.KritaText,

            # krita/debug
            nodes.KritaDebug,

            # krita/ui
            ui.KritaUiBoolean,
            ui.KritaUiCombo,
            ui.KritaUiFloat,
            ui.KritaUiInt,
            ui.KritaUiLayerId,
            ui.KritaUiString,

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
        ]

async def comfy_entrypoint() -> KritaComfyui:
    return KritaComfyui()


__all__ = [
    "comfy_entrypoint",
]

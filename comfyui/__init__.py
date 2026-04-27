from comfy_api.latest import ComfyExtension, io

from .src.krita_comfyui import nodes, ui


class KritaComfyui(ComfyExtension):
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            # util
            nodes.LoadImageBase64,
            nodes.LoadMaskBase64,
            nodes.ThrowError,

            # ui
            ui.KritaUiBoolean,
            ui.KritaUiCombo,
            ui.KritaUiFloat,
            ui.KritaUiInt,
            ui.KritaUiLayerName,
            ui.KritaUiString,

            # krita
            nodes.KritaConnect,
            nodes.KritaCanvas,
            nodes.KritaLayers,
            nodes.KritaSeed,
            nodes.KritaSelection,
            nodes.KritaOutput,
        ]

async def comfy_entrypoint() -> KritaComfyui:
    return KritaComfyui()


WEB_DIRECTORY = "./js"

__all__ = [
    "comfy_entrypoint",
    "WEB_DIRECTORY",
]

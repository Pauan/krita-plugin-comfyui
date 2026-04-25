from comfy_api.latest import ComfyExtension, io

from .src.krita_comfyui import nodes, ui


class KritaComfyui(ComfyExtension):
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            # image
            nodes.LoadImageBase64,

            # ui
            ui.KritaUiRoot,
            ui.KritaUiRow,
            ui.KritaUiGroup,
            ui.KritaUiList,
            ui.KritaUiBoolean,
            ui.KritaUiCombo,
            ui.KritaUiFloat,
            ui.KritaUiInt,
            ui.KritaUiLayer,
            ui.KritaUiString,

            # krita
            nodes.KritaConnect,
            nodes.KritaCanvas,
            nodes.KritaLayers,
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

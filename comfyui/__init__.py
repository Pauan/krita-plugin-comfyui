from comfy_api.latest import ComfyExtension, io

from .src.krita_comfyui import nodes


class KritaComfyui(ComfyExtension):
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            # krita
            nodes.KritaConnect,
            nodes.KritaLayers,
            #krita.KritaSelection,
            #krita.KritaCanvas,
            #krita.KritaOutput,
        ]

async def comfy_entrypoint() -> KritaComfyui:
    return KritaComfyui()


WEB_DIRECTORY = "./js"

__all__ = [
    "comfy_entrypoint",
    "WEB_DIRECTORY",
]

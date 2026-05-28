from . import root, clean, build_krita, build_comfyui
from .workflows.upscale import Upscale

Upscale(root).write()

clean()
build_comfyui()
build_krita()

from . import root, build_krita, build_comfyui, build_shared
from .workflows.upscale import Upscale

Upscale(root).write()

build_krita()
build_comfyui()
build_shared()

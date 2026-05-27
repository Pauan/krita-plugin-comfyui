from . import root, build_krita, build_comfyui, build_shared, generate_workflows

generate_workflows.Upscale(root).write()

build_krita()
build_comfyui()
build_shared()

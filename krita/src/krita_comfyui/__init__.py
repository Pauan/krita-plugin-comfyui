"""ComfyUI integration for Krita"""

import sys
from pathlib import Path

# Enables Python to load dependencies
sys.path.append(str(Path(__file__).parent / "site-packages"))


import krita
from .extension import (ComfyUIExtension)
from .dock import (ComfyUIOutputWidget)

instance = krita.Krita.instance()

instance.addExtension(ComfyUIExtension(instance))

instance.addDockWidgetFactory(
    krita.DockWidgetFactory("krita_comfyui_outputs", krita.DockWidgetFactoryBase.DockPosition.DockLeft, ComfyUIOutputWidget)
)

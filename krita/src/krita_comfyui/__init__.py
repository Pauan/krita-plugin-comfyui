"""ComfyUI integration for Krita"""

import sys
from pathlib import Path

# Enables Python to load dependencies
sys.path.append(str(Path(__file__).parent / "site-packages"))


import krita
from .extension import (ComfyUIExtension)

instance = Krita.instance()

instance.addExtension(ComfyUIExtension(instance))

#Krita.instance().addDockWidgetFactory(
#    DockWidgetFactory("comfyui", DockWidgetFactoryBase.DockPosition.DockRight, DockWidget)
#)

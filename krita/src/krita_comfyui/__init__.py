"""ComfyUI integration for Krita"""

print("STARTING UP")

import sys
from pathlib import Path

# Enables Python to load dependencies
sys.path.append(str(Path(__file__).parent / "site-packages"))

print(sys.path)

__version__ = "1.0.0"

import krita

from .extension import (ComfyUIExtension)

Krita.instance().addExtension(ComfyUIExtension(Krita.instance()))

print("REGISTERED")

#Krita.instance().addDockWidgetFactory(
#    DockWidgetFactory("comfyui", DockWidgetFactoryBase.DockPosition.DockRight, DockWidget)
#)

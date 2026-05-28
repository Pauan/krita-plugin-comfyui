from typing import Any

class _MetaKrita(type):
    # Causes all class attributes to return Any
    def __getattr__(cls, item) -> Any:
        ...

class Krita(metaclass=_MetaKrita):
    ...

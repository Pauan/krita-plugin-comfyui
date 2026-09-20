from collections.abc import Callable, Mapping
from typing import Any

def simple_eval(
    expr: str,
    operators: Mapping[type, Callable[..., Any]] | None = None,
    functions: Mapping[str, Callable[..., Any]] | None = None,
    names: Mapping[str, Any] | Callable[..., Any] | None = None,
    allowed_attrs: Mapping[type, Any] | None = None,
) -> Any: ...

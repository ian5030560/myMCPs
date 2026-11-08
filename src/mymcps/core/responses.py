"""Reading a model response, which LiteLLM gives as an object or as a plain dict."""

from __future__ import annotations

from typing import Any


def field(obj: Any, name: str) -> Any:
    """``obj[name]`` for a dict, ``obj.name`` otherwise; ``None`` when it is not there."""
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)

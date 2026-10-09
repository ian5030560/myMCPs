"""Thin wrapper around LiteLLM. This is the ONLY module that imports ``litellm``.

LiteLLM is imported lazily (server start-up and ``list_tools`` never pay for it) and with
stdout redirected to stderr so nothing can corrupt the stdio MCP transport.
"""

from __future__ import annotations

import contextlib
import importlib
import logging
import os
import sys
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from .errors import (
    AuthError,
    ModelError,
    ModelNotFoundError,
    ProviderError,
    RateLimitError,
)

if TYPE_CHECKING:
    from .models import ResolvedModel

log = logging.getLogger(__name__)

# capability name -> litellm helper
_CAPABILITY_HELPERS = {
    "vision": "supports_vision",
    "audio_input": "supports_audio_input",
    "video_input": "supports_video_input",
}

# LiteLLM exception class name -> (our error, hint)
_ERROR_MAP = {
    "AuthenticationError": (AuthError, "Check the API key for this provider."),
    "PermissionDeniedError": (AuthError, "The API key lacks permission for this model."),
    "NotFoundError": (ModelNotFoundError, "Check the model name."),
    "RateLimitError": (RateLimitError, "Rate limit or quota exceeded; retry later."),
}

_KEY_HINTS = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "stability": "STABILITY_API_KEY",
}


class LLMClient:
    def __init__(self, module: Any | None = None):
        self._injected = module
        self._loaded: Any | None = None

    # ── lazy import ──────────────────────────────────────────────────────
    @property
    def _module(self) -> Any:
        if self._injected is not None:
            return self._injected
        if self._loaded is None:
            os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
            os.environ.setdefault("LITELLM_TELEMETRY", "False")
            with contextlib.redirect_stdout(sys.stderr):
                mod = importlib.import_module("litellm")
            mod.suppress_debug_info = True
            for name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy", "litellm"):
                lg = logging.getLogger(name)
                lg.handlers = [logging.StreamHandler(sys.stderr)]
                lg.propagate = False
            self._loaded = mod
        return self._loaded

    # ── introspection ────────────────────────────────────────────────────
    def get_provider(self, model: str) -> str:
        try:
            return self._module.get_llm_provider(model)[1]
        except Exception:
            return model.split("/", 1)[0] if "/" in model else "unknown"

    def supports(self, model: str, capability: str) -> bool | None:
        helper = getattr(self._module, _CAPABILITY_HELPERS.get(capability, ""), None)
        if helper is None:
            return None
        try:
            return bool(helper(model))
        except Exception:
            return None

    # ── calls ────────────────────────────────────────────────────────────
    async def complete(self, model: ResolvedModel, messages: list[dict], **kw: Any) -> Any:
        with self._guard(model):
            return await self._module.acompletion(
                model=model.model, messages=messages, **model.call_kwargs(), **kw)

    async def generate_image(self, model: ResolvedModel, prompt: str, **kw: Any) -> Any:
        with self._guard(model):
            return await self._module.aimage_generation(
                model=model.model, prompt=prompt, **model.call_kwargs(), **kw)

    async def edit_image(self, model: ResolvedModel, image: Any, prompt: str, **kw: Any) -> Any:
        with self._guard(model):
            return await self._module.aimage_edit(
                model=model.model, image=image, prompt=prompt, **model.call_kwargs(), **kw)

    async def transcribe(self, model: ResolvedModel, file: Any, **kw: Any) -> Any:
        with self._guard(model):
            return await self._module.atranscription(
                model=model.model, file=file, **model.call_kwargs(), **kw)

    async def upload_file(self, model: ResolvedModel, file: Any, purpose: str = "user_data",
                          **kw: Any) -> Any:
        with self._guard(model):
            return await self._module.acreate_file(
                file=file, purpose=purpose, custom_llm_provider=model.provider,
                **model.call_kwargs(), **kw)

    # ── error translation ────────────────────────────────────────────────
    @contextlib.contextmanager
    def _guard(self, model: ResolvedModel) -> Iterator[None]:
        try:
            yield
        except ModelError:
            raise
        except Exception as exc:
            raise self._translate_error(exc, model) from exc

    @staticmethod
    def _translate_error(exc: Exception, model: ResolvedModel) -> ModelError:
        for cls in type(exc).__mro__:
            if cls.__name__ in _ERROR_MAP:
                err_cls, hint = _ERROR_MAP[cls.__name__]
                if err_cls is AuthError and model.provider in _KEY_HINTS:
                    hint = f"Set the {_KEY_HINTS[model.provider]} environment variable."
                return err_cls(f"{model.model}: {_short(exc)} ({hint})")
        return ProviderError(f"{model.model}: {_short(exc)}")


def _short(exc: Exception, limit: int = 500) -> str:
    text = str(exc).strip() or type(exc).__name__
    return text if len(text) <= limit else text[:limit] + "…"

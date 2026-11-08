"""Thin wrapper around LiteLLM. This is the ONLY module that imports ``litellm``.

LiteLLM is imported lazily (importing a server, ``list_tools`` and a server with no model
configured never pay for it; the startup purpose check does when a model is configured) and with
stdout redirected to stderr so nothing can corrupt the stdio MCP transport.
"""

from __future__ import annotations

import contextlib
import importlib
import logging
import os
import re
import sys
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from .abilities import TableEntry
from .errors import (
    AuthError,
    ModelError,
    ModelNotFoundError,
    ProviderError,
    RateLimitError,
)
from .responses import (
    GeneratedImage,
    Transcription,
    completion_text,
    file_id_from,
    images_from,
    transcription_from,
)
from .vendors import STANDARD_KEY_VARS

if TYPE_CHECKING:
    from .models import ResolvedModel

log = logging.getLogger(__name__)

# LiteLLM reports a missing key as APIConnectionError("GEMINI_API_KEY is not set"), not as an
# authentication error, so it is recognised by its message.
_KEY_MISSING = re.compile(r"api[_ ]?key.{0,40}(not set|missing|not provided|required)", re.I)

# LiteLLM exception class name -> (our error, hint)
_ERROR_MAP = {
    "AuthenticationError": (AuthError, "Check the API key for this provider."),
    "PermissionDeniedError": (AuthError, "The API key lacks permission for this model."),
    "NotFoundError": (ModelNotFoundError, "Check the model name."),
    "RateLimitError": (RateLimitError, "Rate limit or quota exceeded; retry later."),
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
    def get_vendor(self, model: str) -> str:
        """The vendor LiteLLM routes a model string to (for names without a ``vendor/`` prefix)."""
        try:
            return self._module.get_llm_provider(model)[1]
        except Exception:
            return model.split("/", 1)[0] if "/" in model else "unknown"

    def table_entry(self, model: str) -> TableEntry | None:
        """What LiteLLM's model table says about ``model``, or None if it is not in the table.

        The table is read directly because LiteLLM's ``supports_*`` helpers answer "no" for models
        they do not know. OpenAI models are listed without their ``openai/`` prefix.
        """
        try:
            table = self._module.model_cost
            entry = table.get(model)
            if entry is None and model.startswith("openai/"):
                entry = table.get(model.removeprefix("openai/"))
        except Exception:
            return None
        if not isinstance(entry, dict):
            return None
        return TableEntry(mode=entry.get("mode"), vision=bool(entry.get("supports_vision")),
                          audio_input=bool(entry.get("supports_audio_input")))

    # ── calls ────────────────────────────────────────────────────────────
    async def complete(self, model: ResolvedModel, messages: list[dict], **kw: Any) -> str:
        """The answer text (stripped; empty when the model said nothing)."""
        with self._guard(model):
            response = await self._module.acompletion(
                model=model.model, messages=messages, **model.call_kwargs(), **kw)
        text = completion_text(response)
        if text is None:
            raise ProviderError(f"{model.model} returned no answer.")
        return text

    async def generate_image(self, model: ResolvedModel, prompt: str,
                             **kw: Any) -> list[GeneratedImage]:
        with self._guard(model):
            response = await self._module.aimage_generation(
                model=model.model, prompt=prompt, **model.call_kwargs(), **kw)
        return images_from(response)

    async def edit_image(self, model: ResolvedModel, image: Any, prompt: str,
                         **kw: Any) -> list[GeneratedImage]:
        with self._guard(model):
            response = await self._module.aimage_edit(
                model=model.model, image=image, prompt=prompt, **model.call_kwargs(), **kw)
        return images_from(response)

    async def transcribe(self, model: ResolvedModel, file: Any, **kw: Any) -> Transcription:
        with self._guard(model):
            response = await self._module.atranscription(
                model=model.model, file=file, **model.call_kwargs(), **kw)
        return transcription_from(response)

    async def upload_file(self, model: ResolvedModel, file: Any, purpose: str = "user_data",
                          **kw: Any) -> str:
        """Upload ``file`` to the vendor and return its id."""
        with self._guard(model):
            response = await self._module.acreate_file(
                file=file, purpose=purpose, custom_llm_provider=model.vendor,
                **model.call_kwargs(), **kw)
        file_id = file_id_from(response)
        if not file_id:
            raise ProviderError(f"{model.model}: the upload returned no file id.")
        return file_id

    async def delete_file(self, model: ResolvedModel, file_id: str, **kw: Any) -> None:
        """Remove a file uploaded with :meth:`upload_file` from the vendor."""
        with self._guard(model):
            await self._module.afile_delete(
                file_id=file_id, custom_llm_provider=model.vendor, **model.call_kwargs(), **kw)

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
        text = _short(exc)
        for cls in type(exc).__mro__:
            if cls.__name__ in _ERROR_MAP:
                err_cls, hint = _ERROR_MAP[cls.__name__]
                break
        else:
            if not _KEY_MISSING.search(text):
                return ProviderError(f"{model.model}: {text}")
            err_cls, hint = _ERROR_MAP["AuthenticationError"]
        if err_cls is AuthError:
            if model.provider.api_key:
                hint = f"Check the api_key of provider `{model.provider.name}`."
            elif model.provider.key_variable:
                hint = (f"Set the {model.provider.key_variable} environment variable "
                        f"(the api_key of provider `{model.provider.name}`).")
            elif model.vendor in STANDARD_KEY_VARS:
                hint = f"Set the {STANDARD_KEY_VARS[model.vendor]} environment variable."
        error = err_cls(f"{model.model}: {text} ({hint})")
        if isinstance(error, RateLimitError):
            error.retry_after = _retry_after(exc, text)
        return error


_RETRY_HINT = re.compile(r"retry(?:ing)?\s+(?:in|after)\s+(\d+(?:\.\d+)?)\s*(ms|s|sec|seconds?)?",
                         re.I)


def _retry_after(exc: Exception, text: str) -> float | None:
    """The wait a provider asked for: a ``Retry-After`` header, else "retry in 51s" in the text."""
    headers = getattr(getattr(exc, "response", None), "headers", None)
    try:
        value = headers.get("retry-after") if headers is not None else None
        if value is not None:
            return max(float(value), 0.0)
    except (TypeError, ValueError, AttributeError):
        pass
    found = _RETRY_HINT.search(text)
    if not found:
        return None
    seconds = float(found.group(1))
    return seconds / 1000 if (found.group(2) or "").lower() == "ms" else seconds


def _short(exc: Exception, limit: int = 500) -> str:
    """The message for the agent: LiteLLM sometimes embeds a whole traceback in it, which is
    noise (and would be cut off mid-line), so only the text before it is kept."""
    text = str(exc).split("Traceback (most recent call last)")[0].strip()
    text = text or type(exc).__name__
    return text if len(text) <= limit else text[:limit] + "…"

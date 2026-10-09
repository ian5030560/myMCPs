"""Model alias resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .config import DEFAULT_MODELS, ModelSpec, Settings

if TYPE_CHECKING:
    from .llm import LLMClient

# purpose -> (section attribute, DEFAULT_MODELS key)
_PURPOSES = {
    "default": ("default_model", None),
    "transcription": ("transcription_model", "transcription"),
}


@dataclass(frozen=True)
class ResolvedModel:
    alias: str
    model: str
    provider: str
    capabilities: frozenset[str] = frozenset()
    api_base: str | None = None
    api_key: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    _llm: LLMClient | None = field(default=None, repr=False, compare=False)

    def call_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = dict(self.extra)
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.api_key:
            kwargs["api_key"] = self.api_key
        return kwargs

    def supports(self, capability: str) -> bool | None:
        """True/False if known, None if unknown. Config declarations win over LiteLLM's table."""
        if capability in self.capabilities:
            return True
        if self._llm is not None:
            return self._llm.supports(self.model, capability)
        return None


class ModelRegistry:
    def __init__(self, settings: Settings, llm: LLMClient, environ=None):
        self._settings = settings
        self._llm = llm
        self._environ = os.environ if environ is None else environ

    def resolve(self, server: str, model: str | None = None,
                purpose: str = "default") -> ResolvedModel:
        name = model or self._default_name(server, purpose)
        spec = self._settings.models.get(name)
        if spec is None:
            spec = ModelSpec(model=name)
        return self._build(name, spec)

    def describe(self, server: str) -> list[dict[str, Any]]:
        """Description for the ``list_models`` tool. Never includes keys or URLs."""
        section = self._settings.section(server)
        defaults = {
            "default": section.default_model or DEFAULT_MODELS[server],
        }
        if server == "audio_listen":
            defaults["transcription"] = (
                self._settings.audio_listen.transcription_model or DEFAULT_MODELS["transcription"]
            )
        rows = [
            {"alias": alias, "model": spec.model, "capabilities": spec.capabilities,
             "default_for": [p for p, d in defaults.items() if d == alias]}
            for alias, spec in self._settings.models.items()
        ]
        known = {r["alias"] for r in rows}
        for purpose, name in defaults.items():
            if name not in known:
                rows.append({"alias": name, "model": name, "capabilities": [],
                             "default_for": [purpose]})
        return rows

    def _default_name(self, server: str, purpose: str) -> str:
        attr, fallback_key = _PURPOSES[purpose]
        section = self._settings.section(server)
        name = getattr(section, attr, None)
        if name:
            return name
        return DEFAULT_MODELS[fallback_key or server]

    def _build(self, alias: str, spec: ModelSpec) -> ResolvedModel:
        api_key = spec.api_key
        if spec.api_key_env:
            api_key = self._environ.get(spec.api_key_env) or api_key
        return ResolvedModel(
            alias=alias,
            model=spec.model,
            provider=self._llm.get_provider(spec.model),
            capabilities=frozenset(spec.capabilities),
            api_base=spec.api_base,
            api_key=api_key,
            extra=dict(spec.extra),
            _llm=self._llm,
        )

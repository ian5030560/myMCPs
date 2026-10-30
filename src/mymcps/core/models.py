"""Model alias and provider resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .abilities import derive
from .config import ModelSpec, ProviderSpec, Settings
from .errors import PurposeNotConfiguredError
from .spec import ServerSpec
from .vendors import KNOWN_VENDORS, STANDARD_KEY_VARS, vendor_of

if TYPE_CHECKING:
    from .llm import LLMClient


@dataclass(frozen=True)
class ResolvedProvider:
    """The connection a model goes through. Every resolved model has exactly one."""

    name: str
    vendor: str
    api_base: str | None = None
    api_key: str | None = None
    key_variable: str | None = None    # the variable its api_key named but that had no value
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedModel:
    alias: str
    model: str
    provider: ResolvedProvider
    extra: dict[str, Any] = field(default_factory=dict)   # provider's, then the model's
    _llm: LLMClient | None = field(default=None, repr=False, compare=False)

    @property
    def vendor(self) -> str:
        """The vendor whose API this call speaks. Behaviour that differs per vendor reads this."""
        return self.provider.vendor

    def call_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = dict(self.extra)
        if self.provider.api_base:
            kwargs["api_base"] = self.provider.api_base
        if self.provider.api_key:
            kwargs["api_key"] = self.provider.api_key
        return kwargs

    def abilities(self) -> frozenset[str] | None:
        """What this model can do, derived from LiteLLM's table; None when the table does not
        know it (unknown on every count: such a model is simply tried)."""
        if self._llm is None:
            return None
        return derive(self._llm.table_entry(self.model), self.vendor)

    def supports(self, ability: str) -> bool | None:
        """True/False if the model is known, None if unknown."""
        known = self.abilities()
        return None if known is None else ability in known


class ModelRegistry:
    """Turns a purpose (or an explicit model name) into the model to call."""

    def __init__(self, settings: Settings, llm: LLMClient, server: ServerSpec, environ=None):
        self._settings = settings
        self._llm = llm
        self._server = server
        self._environ = os.environ if environ is None else environ

    def resolve(self, purpose: str, model: str | None = None) -> ResolvedModel:
        """The model for one of this server's purposes.

        ``model`` (a tool argument) wins over the configured ``<purpose>_model``. There is no
        built-in default: an unconfigured purpose is an error that names the field to set.
        """
        wanted = self._server.purpose(purpose)
        name = model or self._settings.section(self._server.name).model_for(wanted)
        if not name:
            raise PurposeNotConfiguredError(self._server.name, wanted.field, wanted.summary)
        return self.resolve_model(name)

    def resolve_model(self, name: str) -> ResolvedModel:
        """A model alias from ``[models.*]``, or else a raw ``vendor/model`` string."""
        spec = self._settings.models.get(name) or ModelSpec(model=name)
        vendor = vendor_of(spec.model) or self._llm.get_vendor(spec.model)
        provider = self._provider_for(spec, vendor)
        return ResolvedModel(
            alias=name,
            model=spec.model,
            provider=provider,
            extra={**provider.extra, **spec.extra},    # the model wins on the same key
            _llm=self._llm,
        )

    def has_key(self, model: ResolvedModel) -> bool:
        """Is a key reachable: one on the provider, or the vendor's standard variable.

        A provider whose configured key did not resolve has no key; the vendor's variable is not
        used instead, because that key belongs to someone else's endpoint.
        """
        if model.provider.api_key:
            return True
        if model.provider.key_variable:
            return False
        variable = STANDARD_KEY_VARS.get(model.vendor)
        return bool(variable and self._environ.get(variable))

    def key_configured(self, model: ResolvedModel) -> bool:
        """False only when a key is expected but unavailable.

        Expected means the vendor has a standard key variable and the connection is LiteLLM's
        own default; a provider with its own endpoint (self-hosted, proxy) may need no key.
        """
        if self.has_key(model):
            return True
        if model.provider.key_variable:     # a key was configured and did not resolve
            return False
        return model.vendor not in STANDARD_KEY_VARS or model.provider.api_base is not None

    def check_purposes(self) -> list[str]:
        """Warnings for configured purposes whose model is known to be the wrong kind.

        Only a model LiteLLM's table knows can fail a check; unknown models are never warned
        about. The server starts either way.
        """
        section = self._settings.section(self._server.name)
        warnings = []
        for purpose in self._server.purposes:
            name = section.model_for(purpose)
            if not name or purpose.need is None:
                continue
            model = self.resolve_model(name)
            found = model.abilities()
            if found is not None and not purpose.need.met(found):
                warnings.append(
                    f"[{self._server.name}] {purpose.field} = `{name}`: this model is known to "
                    f"LiteLLM as {', '.join(sorted(found)) or 'something else'}, but "
                    f"{purpose.summary} needs {purpose.need.description}.")
        return warnings

    def describe(self) -> dict[str, Any]:
        """Description for the ``list_models`` tool. Never includes keys or URLs."""
        section = self._settings.section(self._server.name)
        purposes = []
        used: dict[str, list[str]] = {}
        for purpose in self._server.purposes:
            name = section.model_for(purpose)
            purposes.append({
                "purpose": purpose.name,
                "field": purpose.field,
                "summary": purpose.summary,
                "configured": bool(name),
                "model": name or "not configured",
            })
            if name:
                used.setdefault(name, []).append(purpose.name)
        models = []
        for alias, spec in self._settings.models.items():
            resolved = self.resolve_model(alias)
            models.append({
                "alias": alias,
                "model": spec.model,
                "provider": resolved.provider.name,
                "vendor": resolved.vendor,
                "key_configured": self.key_configured(resolved),
                "abilities": sorted(known) if (known := resolved.abilities()) is not None
                else "unknown",
                "used_for": used.get(alias, []),
            })
        return {"purposes": purposes, "models": models}

    def _provider_for(self, spec: ModelSpec, vendor: str) -> ResolvedProvider:
        """The explicit link, else the provider named after the vendor, else LiteLLM's default."""
        providers = self._settings.providers
        if spec.provider:
            name = spec.provider
            chosen = providers[name]
        elif vendor in KNOWN_VENDORS and vendor in providers:
            name, chosen = vendor, providers[vendor]
        else:
            return ResolvedProvider(name=vendor, vendor=vendor)
        return self._resolved(name, chosen, vendor)

    def _resolved(self, name: str, provider: ProviderSpec, model_vendor: str) -> ResolvedProvider:
        return ResolvedProvider(
            name=name,
            vendor=provider.vendor or model_vendor,
            api_base=provider.api_base,
            api_key=provider.api_key or None,
            key_variable=self._settings.key_variables.get(name),
            extra=dict(provider.extra),
        )

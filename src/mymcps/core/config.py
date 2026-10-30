"""Settings model and loader.

Settings come from the TOML file only; the one environment variable read is MYMCPS_CONFIG, which
names the file. The loader validates strictly, but only what the running server uses: the
top-level settings, the model aliases and the server's own section. Every problem is collected
and reported together (:class:`ConfigError`), each naming file, section and field, never a value.
"""

from __future__ import annotations

import difflib
import os
import sys
import tempfile
from collections.abc import Collection, Iterator, Mapping
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from .errors import ConfigError
from .spec import Purpose, ServerSpec
from .variables import BUILTIN_VARIABLES, VariableExpander
from .vendors import KNOWN_VENDORS, vendor_of

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

SERVER_ENTRY_POINT_GROUP = "mymcps.servers"

# Top-level keys that belong to the config itself. Every other top-level table is the section
# of the server it is named after.
GLOBAL_KEYS = frozenset({"output_dir", "max_download_mb", "providers", "models"})

# The part of the config only a server with purposes reads. A server without any (say a file
# converter) does not read, expand or validate these, so a broken provider cannot stop it.
MODEL_KEYS = frozenset({"providers", "models"})

# A typo scores 0.8 or more against the name it was meant to be; a valid field of another server
# (say `watch_model` in the image section) scores 0.67 or less. 0.75 keeps the hint honest.
SUGGESTION_CUTOFF = 0.75

# What a project layer may not set: it can choose models and output folders, never where data
# goes (ADR 0002). Its aliases may set only a model string and a link to a global provider.
PROJECT_FORBIDDEN = frozenset({"providers", "max_download_mb"})
PROJECT_MODEL_FIELDS = frozenset({"model", "provider"})


# Names from the earlier layout. They are not accepted any more; an error that meets one says what
# replaced it and points to the README ("Migrating"), so nothing fails mysteriously.
MIGRATION_POINTER = "See \"Migrating\" in the README."
LEGACY_SECTIONS = {
    "image_gen": "image", "video_watch": "video", "audio_listen": "audio",
}
_MOVED = "moved to a provider: define [providers.<name>] and link it with provider = <name>"
LEGACY_FIELDS = {
    "default_model": "set one model per job instead: `<job>_model` in the server's section",
    "image_model": "use `gen_model` / `edit_model` in `[image]`",
    "video_model": "use `watch_model` in `[video]`",
    "audio_model": "use `listen_model` in `[audio]`",
    "transcription_model": "use `transcribe_model` in `[audio]`",
    "allowed_dirs": "removed: the servers no longer restrict which files a tool may read",
    "api_key_env": "removed: write api_key = \"${VAR}\" in the provider",
    "capabilities": "removed: what a model can do is derived from LiteLLM's table",
    "api_base": _MOVED,
    "api_key": _MOVED,
}
LEGACY_ENV_PREFIX = "MYMCPS_"


def legacy_environment(environ: Mapping[str, str]) -> list[str]:
    """Settings environment variables of the earlier layout that are set but no longer read."""
    return sorted(name for name in environ
                  if name.startswith(LEGACY_ENV_PREFIX) and name != SettingsLoader.ENV_CONFIG)


def discover_server_names() -> set[str]:
    """Names of all servers in this installation (read from package metadata, nothing imported)."""
    return {ep.name for ep in entry_points(group=SERVER_ENTRY_POINT_GROUP)}


class ProviderSpec(BaseModel):
    """One ``[providers.<name>]`` entry: connection details shared by several models."""

    model_config = ConfigDict(extra="forbid")

    vendor: str | None = None      # which vendor's API it speaks; see _providers_with_vendors
    api_base: str | None = None
    api_key: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)   # passed on untouched, never validated


class ModelSpec(BaseModel):
    """One ``[models.<alias>]`` entry."""

    model_config = ConfigDict(extra="forbid")

    model: str
    provider: str | None = None    # explicit link to a provider
    extra: dict[str, Any] = Field(default_factory=dict)   # passed on untouched, never validated


class GlobalConfig(BaseModel):
    """The top-level settings every server reads."""

    model_config = ConfigDict(extra="forbid")

    output_dir: str | None = None
    max_download_mb: int = 4096
    providers: dict[str, ProviderSpec] = Field(default_factory=dict)
    models: dict[str, ModelSpec] = Field(default_factory=dict)


class ServerSection(BaseModel):
    """One server's section as held by :class:`Settings`. Its ``<purpose>_model`` fields depend
    on the server, so they are kept as extra fields and read through :meth:`model_for`. The
    loader checks them strictly against the server's declaration before they get here."""

    model_config = ConfigDict(extra="allow")

    output_dir: str | None = None

    def model_for(self, purpose: Purpose) -> str | None:
        value = (self.model_extra or {}).get(purpose.field)
        return str(value) if value else None


class Settings(BaseModel):
    output_dir: str | None = None
    max_download_mb: int = 4096
    providers: dict[str, ProviderSpec] = Field(default_factory=dict)
    models: dict[str, ModelSpec] = Field(default_factory=dict)
    sections: dict[str, ServerSection] = Field(default_factory=dict)
    # provider name -> the variable its `api_key` named but that had no value (that key is "no key")
    key_variables: dict[str, str] = Field(default_factory=dict)
    # the files that were loaded, in merge order: (layer, path); never any value
    sources: list[tuple[str, str]] = Field(default_factory=list)

    def section(self, server_name: str) -> ServerSection:
        return self.sections.get(server_name) or ServerSection()


def _strict_section(server: ServerSpec) -> type[BaseModel]:
    """The exact set of fields this server's section may contain."""
    fields: dict[str, Any] = {"output_dir": (str | None, None)}
    for purpose in server.purposes:
        fields[purpose.field] = (str | None, None)
    return create_model(
        f"{server.name}Section", __config__=ConfigDict(extra="forbid"), **fields)


@dataclass
class _Layer:
    """One config file, validated and ready to be merged."""

    kind: str                      # "shared" | "server" | "project"
    path: Path
    output_dir: str | None = None
    max_download_mb: int | None = None
    providers: dict[str, ProviderSpec] = field(default_factory=dict)
    models: dict[str, ModelSpec] = field(default_factory=dict)
    section: dict[str, Any] | None = None
    key_variables: dict[str, str] = field(default_factory=dict)


class SettingsLoader:
    """Reads the layers of the config, checks each file on its own, then merges them.

    Merge order is the shared file, the server file, the project layer. Single values are
    overridden by the later file, a section is merged field by field, and providers and model
    aliases merge by name with the whole entry replaced.
    """

    ENV_CONFIG = "MYMCPS_CONFIG"   # the only environment variable the config reads

    def __init__(self, server: ServerSpec, config_path: str | Path | None = None,
                 environ: Mapping[str, str] | None = None,
                 known_servers: Collection[str] | None = None,
                 project_path: str | Path | None = None):
        self._server = server
        self._config_path = Path(config_path) if config_path else None
        self._project_path = Path(project_path) if project_path else None
        self._environ = os.environ if environ is None else environ
        discovered = discover_server_names() if known_servers is None else set(known_servers)
        self._known = discovered | {server.name}
        self._section_model = _strict_section(server)

    def load(self) -> Settings:
        problems: list[str] = []
        layers: list[_Layer] = []
        for kind, path, named_by in self._files():
            data = self._read(path, named_by, problems)
            layer = None if data is None else self._parse(kind, path, data, problems)
            if layer is not None:
                layers.append(layer)
        settings = self._merge(layers, problems)
        if problems:
            raise ConfigError(problems)
        return settings

    # ── finding and reading the files ────────────────────────────────────
    def _files(self) -> Iterator[tuple[str, Path, str | None]]:
        """(layer, path, how it was named) in merge order. Missing default files are skipped."""
        if self._config_path:
            # A file named explicitly is the whole global layer: no server file next to it.
            yield "shared", self._config_path.expanduser(), "--config"
        elif self._environ.get(self.ENV_CONFIG):
            yield "shared", Path(self._environ[self.ENV_CONFIG]).expanduser(), self.ENV_CONFIG
        else:
            home = Path.home() / ".mymcps"
            for kind, path in (("shared", home / "config.toml"),
                               ("server", home / f"{self._server.name}.toml")):
                if path.is_file():
                    yield kind, path, None
        if self._project_path:
            yield "project", self._project_path.expanduser(), "--project-config"

    @staticmethod
    def _read(path: Path, named_by: str | None, problems: list[str]) -> dict[str, Any] | None:
        if named_by and not path.is_file():
            problems.append(f"Config file not found: {path} (named by {named_by}).")
            return None
        try:
            with open(path, "rb") as fh:
                return tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            problems.append(f"{path}: invalid TOML: {exc}")
        except OSError as exc:
            problems.append(f"{path}: cannot read the file: {exc.strerror or exc}")
        return None

    # ── checking one file ────────────────────────────────────────────────
    def _parse(self, kind: str, path: Path, data: dict[str, Any],
               problems: list[str]) -> _Layer | None:
        top: dict[str, Any] = {}
        own: dict[str, Any] | None = None
        key_variables: dict[str, str] = {}

        for key, value in data.items():
            if key in MODEL_KEYS and not self._server.purposes:
                continue
            if key in GLOBAL_KEYS:
                if kind == "project" and key in PROJECT_FORBIDDEN:
                    problems.append(self._line(path, (), key, (
                        "not allowed in a project layer; it can choose models and output "
                        "folders but never where data is sent.")))
                else:
                    top[key] = value
            elif isinstance(value, dict):
                if key == self._server.name:
                    own = value
                elif key not in self._known:
                    problems.append(self._unknown_section(path, key))
                elif kind != "shared":
                    problems.append(
                        f"{path}: [{key}]: a {kind} file may only hold its own server's "
                        f"section ([{self._server.name}]).")
                # else: another server's section in the shared file. None of this server's business.
            else:
                problems.append(self._unknown_field(path, (), key))

        if kind == "project":
            self._screen_project_models(path, top, problems)

        # Only what this server uses is expanded, so another server's variables cannot stop it.
        expander = self._expander(path)
        top = self._expand_all(path, expander, top, (), problems, key_variables, kind)
        if own is not None:
            own = self._expand_all(
                path, expander, own, (self._server.name,), problems, key_variables, kind)

        checked_top = self._check(path, GlobalConfig, top, (), problems)
        checked_own = None
        if own is not None:
            checked_own = self._check(
                path, self._section_model, own, (self._server.name,), problems)
        if checked_top is None:     # the rest is still checked so every problem is reported
            return None

        base = path.resolve().parent
        given = checked_top.model_fields_set
        output_dir = self._beside(base, checked_top.output_dir) if "output_dir" in given else None
        layer = _Layer(
            kind, path,
            output_dir=output_dir,
            max_download_mb=checked_top.max_download_mb if "max_download_mb" in given else None,
            providers=checked_top.providers, models=checked_top.models,
            key_variables=key_variables)
        if checked_own is not None:
            layer.section = checked_own.model_dump(exclude_none=True)
            if layer.section.get("output_dir"):
                layer.section["output_dir"] = self._beside(base, layer.section["output_dir"])
        return layer

    def _screen_project_models(self, path: Path, top: dict[str, Any],
                               problems: list[str]) -> None:
        """An alias in a project layer sets only `model` and `provider`; anything else is refused
        (and dropped here so it is not reported a second time)."""
        models = top.get("models")
        if not isinstance(models, dict):
            return
        for alias, spec in models.items():
            if not isinstance(spec, dict):
                continue
            for name in [k for k in spec if k not in PROJECT_MODEL_FIELDS]:
                del spec[name]
                if name in ModelSpec.model_fields or name in ProviderSpec.model_fields:
                    problems.append(self._line(path, ("models", str(alias)), name, (
                        "not allowed in a project layer; an alias there may only set "
                        "`model` and `provider`.")))
                else:
                    problems.append(self._unknown_field(path, ("models", str(alias)), name))

    # ── merging ──────────────────────────────────────────────────────────
    def _merge(self, layers: list[_Layer], problems: list[str]) -> Settings:
        output_dir: str | None = None
        max_download_mb = GlobalConfig.model_fields["max_download_mb"].default
        providers: dict[str, ProviderSpec] = {}
        models: dict[str, ModelSpec] = {}
        section: dict[str, Any] = {}
        has_section = False
        key_variables: dict[str, str] = {}
        origins: dict[tuple[str, str], Path] = {}

        for layer in layers:
            if layer.output_dir is not None:
                output_dir = layer.output_dir
            if layer.max_download_mb is not None:
                max_download_mb = layer.max_download_mb
            for name, provider in layer.providers.items():     # the whole entry is replaced
                providers[name] = provider
                origins[("providers", name)] = layer.path
                if name in layer.key_variables:
                    key_variables[name] = layer.key_variables[name]
                else:
                    key_variables.pop(name, None)
            for alias, model in layer.models.items():
                models[alias] = model
                origins[("models", alias)] = layer.path
            if layer.section is not None:
                has_section = True
                section.update(layer.section)

        settled = self._providers_with_vendors(
            origins, GlobalConfig(providers=providers, models=models), problems)
        return Settings(
            output_dir=output_dir,
            max_download_mb=max_download_mb,
            providers=settled,
            models=models,
            sections={self._server.name: section} if has_section else {},
            key_variables=key_variables,
            sources=[(layer.kind, str(layer.path)) for layer in layers],
        )

    # ── variables and paths ──────────────────────────────────────────────
    def _expander(self, path: Path) -> VariableExpander:
        return VariableExpander({
            "CONFIG_DIR": str(path.resolve().parent),
            "CWD": os.getcwd(),
            "TEMP": tempfile.gettempdir(),
            "SERVER": self._server.name,
        }, self._environ)

    def _expand_all(self, path: Path, expander: VariableExpander, value: Any,
                    where: tuple[str, ...], problems: list[str],
                    key_variables: dict[str, str], kind: str) -> Any:
        """``value`` with ``${NAME}`` expanded in every string, however deeply nested.

        An undefined variable is an error naming file, section and field, except in a provider's
        ``api_key``: there it means "no key" and the variable's name is remembered. A project
        layer expands only the built-in variables, never environment variables.
        """
        if isinstance(value, dict):
            return {key: self._expand_all(path, expander, item, where + (str(key),), problems,
                                          key_variables, kind) for key, item in value.items()}
        if isinstance(value, list):
            return [self._expand_all(path, expander, item, where + (str(i),), problems,
                                     key_variables, kind) for i, item in enumerate(value)]
        if not isinstance(value, str):
            return value
        is_key = len(where) == 3 and where[0] == "providers" and where[2] == "api_key"
        done = expander.expand(value, tilde=not is_key, environment=kind != "project")
        section, field_name = where[:-1], where[-1]
        for name in done.malformed:
            problems.append(self._line(
                path, section, field_name, f"`${{{name}}}` is not a valid variable reference."))
        if is_key and done.undefined:
            key_variables[where[1]] = done.undefined[0]
            return ""
        for name in done.undefined:
            problems.append(self._line(path, section, field_name, (
                f"`{name}` is not a built-in variable; a project layer expands only "
                f"{', '.join(BUILTIN_VARIABLES)}." if kind == "project"
                else f"the variable `{name}` is not defined.")))
        return done.text

    @staticmethod
    def _beside(base: Path, folder: str | None) -> str | None:
        """A relative folder in a config file is relative to the file, not to the process."""
        if not folder or Path(folder).is_absolute():
            return folder
        return str(base / folder)

    def _providers_with_vendors(self, origins: Mapping[tuple[str, str], Path], top: GlobalConfig,
                                problems: list[str]) -> dict[str, ProviderSpec]:
        """Check aliases and providers against each other and settle every provider's vendor.

        A provider's vendor is its name when that is a known vendor, else the one it states, else
        the one its linked models share. Links to nothing, and links across vendors, are errors.
        Each problem names the file the offending alias or provider was written in.
        """
        for alias in top.models:
            if "/" in alias:
                problems.append(self._line(
                    origins[("models", alias)], ("models",), alias,
                    "an alias name cannot contain `/`; it would look like a raw model string."))

        linked: dict[str, list[tuple[str, str | None]]] = {}
        for alias, model in top.models.items():
            if model.provider is None:
                continue
            if model.provider not in top.providers:
                defined = ", ".join(sorted(top.providers)) or "none"
                problems.append(self._line(
                    origins[("models", alias)], ("models", alias), "provider",
                    f"no provider named `{model.provider}` is defined (defined: {defined})."))
                continue
            linked.setdefault(model.provider, []).append((alias, vendor_of(model.model)))

        settled: dict[str, ProviderSpec] = {}
        for name, provider in top.providers.items():
            where = origins[("providers", name)]
            named = name if name in KNOWN_VENDORS else None
            if named and provider.vendor and provider.vendor != named:
                problems.append(self._line(
                    where, ("providers", name), "vendor",
                    f"`{name}` is a vendor name, so this provider speaks {named}; "
                    f"it cannot state vendor `{provider.vendor}`."))
            vendor = named or provider.vendor
            if vendor is None:
                seen = sorted({v for _, v in linked.get(name, []) if v})
                if len(seen) > 1:
                    problems.append(self._line(
                        where, ("providers", name), "vendor",
                        f"the models linked to it speak different vendors ({', '.join(seen)}); "
                        "state which one the provider speaks with `vendor`."))
                elif seen:
                    vendor = seen[0]
            for alias, model_vendor in linked.get(name, []):
                if vendor and model_vendor and model_vendor != vendor:
                    problems.append(self._line(
                        origins[("models", alias)], ("models", alias), "provider",
                        f"this is a {model_vendor} model but provider `{name}` speaks {vendor}."))
            settled[name] = provider.model_copy(update={"vendor": vendor})
        return settled

    def _check(self, path: Path, model: type[BaseModel], data: dict[str, Any],
               prefix: tuple[str, ...], problems: list[str]) -> Any:
        """Validate ``data`` against ``model``, adding one problem per error. None on failure."""
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            # include_input=False: an error message must never repeat a value from the file.
            for err in exc.errors(include_url=False, include_context=False, include_input=False):
                loc = tuple(str(part) for part in err["loc"])
                section, field = prefix + loc[:-1], (loc[-1] if loc else "")
                if err["type"] == "extra_forbidden":
                    problems.append(self._unknown_field(path, section, field))
                elif err["type"] == "missing":
                    problems.append(self._line(path, section, field, "this field is required"))
                else:
                    problems.append(self._line(path, section, field, err["msg"]))
            return None

    def _valid_fields(self, section: tuple[str, ...]) -> list[str]:
        """The fields allowed in a section, for the 'did you mean' hint."""
        if section == ():
            return sorted(GLOBAL_KEYS)
        if len(section) == 2 and section[0] == "models":
            return list(ModelSpec.model_fields)
        if len(section) == 2 and section[0] == "providers":
            return list(ProviderSpec.model_fields)
        if section == (self._server.name,):
            return list(self._section_model.model_fields)
        return []

    @staticmethod
    def _line(path: Path, section: tuple[str, ...], field: str, text: str) -> str:
        where = f"[{'.'.join(section)}] " if section else ""
        return f"{path}: {where}{field}: {text}"

    def _unknown_field(self, path: Path, section: tuple[str, ...], field: str) -> str:
        options = self._valid_fields(section)
        near = difflib.get_close_matches(field, options, n=1, cutoff=SUGGESTION_CUTOFF)
        suffix = "_model"
        if near:
            head = f"unknown field; did you mean `{near[0]}`?"
        elif section == (self._server.name,) and field.endswith(suffix):
            head = (f"unknown field; the {self._server.name} server has no "
                    f"`{field[:-len(suffix)]}` job.")
        else:
            head = "unknown field."
        if field in LEGACY_FIELDS:
            head += f" This was an old setting; {LEGACY_FIELDS[field]}. {MIGRATION_POINTER}"
        if options:
            head += f" Valid fields here: {', '.join(options)}."
        return self._line(path, section, field, head)

    def _unknown_section(self, path: Path, name: str) -> str:
        options = sorted(self._known)
        near = difflib.get_close_matches(name, options, n=1, cutoff=SUGGESTION_CUTOFF)
        head = f"unknown section; did you mean [{near[0]}]?" if near else "unknown section."
        if name in LEGACY_SECTIONS:
            head = (f"unknown section; the server was renamed, use [{LEGACY_SECTIONS[name]}]. "
                    f"{MIGRATION_POINTER}")
        return f"{path}: [{name}]: {head} Sections are named after servers: {', '.join(options)}."

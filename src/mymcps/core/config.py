"""Settings model and loader (defaults -> TOML -> environment variables)."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

DEFAULT_MODELS = {
    "image_gen": "openai/gpt-image-1",
    "video_watch": "gemini/gemini-2.5-flash",
    "audio_listen": "gemini/gemini-2.5-flash",
    "transcription": "openai/whisper-1",
}

SERVER_KEYS = ("image_gen", "video_watch", "audio_listen")


class ModelSpec(BaseModel):
    """One ``[models.<alias>]`` entry."""

    model: str
    api_base: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class ServerSection(BaseModel):
    default_model: str | None = None
    output_dir: str | None = None


class AudioSection(ServerSection):
    transcription_model: str | None = None


class Settings(BaseModel):
    output_dir: str | None = None
    allowed_dirs: list[Path] = Field(default_factory=list)
    max_download_mb: int = 4096
    models: dict[str, ModelSpec] = Field(default_factory=dict)
    image_gen: ServerSection = Field(default_factory=ServerSection)
    video_watch: ServerSection = Field(default_factory=ServerSection)
    audio_listen: AudioSection = Field(default_factory=AudioSection)

    def section(self, server: str) -> ServerSection:
        if server not in SERVER_KEYS:
            raise KeyError(f"unknown server '{server}'")
        return getattr(self, server)


class SettingsLoader:
    ENV_CONFIG = "MYMCPS_CONFIG"
    ENV_MODELS = {
        "MYMCPS_IMAGE_MODEL": ("image_gen", "default_model"),
        "MYMCPS_VIDEO_MODEL": ("video_watch", "default_model"),
        "MYMCPS_AUDIO_MODEL": ("audio_listen", "default_model"),
        "MYMCPS_TRANSCRIPTION_MODEL": ("audio_listen", "transcription_model"),
    }

    def __init__(self, config_path: str | Path | None = None,
                 environ: Mapping[str, str] | None = None):
        self._config_path = Path(config_path) if config_path else None
        self._environ = os.environ if environ is None else environ

    def load(self) -> Settings:
        data = self._read_toml()
        self._apply_env(data)
        return Settings.model_validate(data)

    def _find_config_file(self) -> Path | None:
        if self._config_path:
            return self._config_path  # explicit path must exist
        env_path = self._environ.get(self.ENV_CONFIG)
        if env_path:
            return Path(env_path)
        default = Path.home() / ".mymcps" / "config.toml"
        return default if default.is_file() else None

    def _read_toml(self) -> dict[str, Any]:
        path = self._find_config_file()
        if path is None:
            return {}
        with open(path.expanduser(), "rb") as fh:
            return tomllib.load(fh)

    def _apply_env(self, data: dict[str, Any]) -> None:
        env = self._environ
        if env.get("MYMCPS_OUTPUT_DIR"):
            data["output_dir"] = env["MYMCPS_OUTPUT_DIR"]
        if env.get("MYMCPS_ALLOWED_DIRS"):
            data["allowed_dirs"] = [p for p in env["MYMCPS_ALLOWED_DIRS"].split(os.pathsep) if p]
        for var, (section, key) in self.ENV_MODELS.items():
            if env.get(var):
                data.setdefault(section, {})[key] = env[var]

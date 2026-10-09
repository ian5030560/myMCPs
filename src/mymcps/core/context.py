"""AppContext: builds and holds the services a server needs (dependency injection point)."""

from __future__ import annotations

from functools import cached_property
from pathlib import Path

from .config import Settings, SettingsLoader
from .ffmpeg import FFmpeg
from .inputs import InputResolver
from .llm import LLMClient
from .models import ModelRegistry
from .outputs import OutputManager


class AppContext:
    def __init__(self, server_name: str, settings: Settings, llm: LLMClient,
                 models: ModelRegistry, inputs: InputResolver, outputs: OutputManager,
                 ffmpeg: FFmpeg | None = None):
        self.server_name = server_name
        self.settings = settings
        self.llm = llm
        self.models = models
        self.inputs = inputs
        self.outputs = outputs
        if ffmpeg is not None:
            self.__dict__["ffmpeg"] = ffmpeg  # pre-seed the cached_property (tests)

    @classmethod
    def create(cls, server_name: str, config_path: str | Path | None = None) -> AppContext:
        settings = SettingsLoader(config_path).load()
        llm = LLMClient()
        inputs = InputResolver(settings)
        return cls(
            server_name=server_name,
            settings=settings,
            llm=llm,
            models=ModelRegistry(settings, llm),
            inputs=inputs,
            outputs=OutputManager(settings, server_name, inputs.check_access),
        )

    @cached_property
    def ffmpeg(self) -> FFmpeg:
        """Created on first use so image-gen does not need imageio-ffmpeg."""
        return FFmpeg.bundled()

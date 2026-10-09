from __future__ import annotations

import pytest

from mymcps.core.config import Settings
from mymcps.core.llm import LLMClient


class FakeLiteLLM:
    """Stands in for the litellm module; records calls."""

    suppress_debug_info = True

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.raises: Exception | None = None

    def get_llm_provider(self, model):
        provider = model.split("/", 1)[0] if "/" in model else "openai"
        return (model, provider, None, None)

    def supports_vision(self, model):
        return model.startswith("gemini/")

    def supports_audio_input(self, model):
        raise RuntimeError("not in table")

    async def _record(self, name, **kw):
        self.calls.append((name, kw))
        if self.raises:
            raise self.raises
        return {"ok": name}

    async def acompletion(self, **kw):
        return await self._record("acompletion", **kw)

    async def aimage_generation(self, **kw):
        return await self._record("aimage_generation", **kw)

    async def aimage_edit(self, **kw):
        return await self._record("aimage_edit", **kw)

    async def atranscription(self, **kw):
        return await self._record("atranscription", **kw)

    async def acreate_file(self, **kw):
        return await self._record("acreate_file", **kw)


@pytest.fixture
def fake_litellm():
    return FakeLiteLLM()


@pytest.fixture
def llm(fake_litellm):
    return LLMClient(module=fake_litellm)


@pytest.fixture
def settings(tmp_path):
    return Settings(output_dir=str(tmp_path / "out"))

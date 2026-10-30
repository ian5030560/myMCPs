from __future__ import annotations

import pytest

from mymcps.core.config import Settings
from mymcps.core.llm import LLMClient


class FakeLiteLLM:
    """Stands in for the litellm module; records calls."""

    suppress_debug_info = True

    def __init__(self):
        # LiteLLM's model table, in miniature: known models, and anything else is unknown.
        # LiteLLM lists OpenAI models without their `openai/` prefix, and its supports_*
        # helpers would answer "no" for a model that is missing here; the code must not use them.
        self.model_cost = {
            "gpt-image-2": {"mode": "image_generation", "supports_vision": True},
            "gemini/gemini-3.1-flash-image": {"mode": "image_generation"},
            "stability/sd3.5-large": {"mode": "image_generation"},
            "stability/inpaint": {"mode": "image_edit"},
            "gemini/gemini-2.5-flash": {"mode": "chat", "supports_vision": True,
                                        "supports_audio_input": True},
            "gpt-4o": {"mode": "chat", "supports_vision": True},
            "gpt-3.5-turbo": {"mode": "chat"},                 # known, and lacking vision/audio
            "whisper-1": {"mode": "audio_transcription"},
        }
        self.calls: list[tuple[str, dict]] = []
        self.raises: Exception | None = None
        self.response = None   # returned by every call when set

    def get_llm_provider(self, model):
        provider = model.split("/", 1)[0] if "/" in model else "openai"
        return (model, provider, None, None)


    async def _record(self, name, **kw):
        self.calls.append((name, kw))
        if self.raises:
            raise self.raises
        return self.response if self.response is not None else {"ok": name}

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


# ── image helpers shared by tests/image ──────────────────────────────
import base64  # noqa: E402
import io  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from PIL import Image  # noqa: E402

from mymcps.core.context import AppContext  # noqa: E402
from mymcps.core.inputs import InputResolver  # noqa: E402
from mymcps.core.models import ModelRegistry  # noqa: E402
from mymcps.core.outputs import OutputManager  # noqa: E402


def png_bytes(size=(64, 48), color="red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def image_response(*images: bytes | str):
    """A LiteLLM-like ImageResponse: bytes -> b64_json, str -> url."""
    data = [SimpleNamespace(b64_json=base64.b64encode(i).decode() if isinstance(i, bytes) else None,
                            url=i if isinstance(i, str) else None, revised_prompt=None)
            for i in images]
    return SimpleNamespace(data=data)


IMAGE_MODELS = {"gen_model": "openai/gpt-image-2", "edit_model": "openai/gpt-image-2"}


@pytest.fixture
def make_ctx(tmp_path, fake_litellm):
    """Build an AppContext wired to the fake LiteLLM.

    ``make_ctx(server=..., sections=..., environ=..., **settings_overrides)``. By default it
    builds the image server with a model configured for each of its purposes; pass
    ``sections={}`` to leave every purpose unconfigured.
    """
    def build(server=None, sections=None, environ=None, **overrides):
        from mymcps.image.server import ImageServer

        server = server or ImageServer.spec
        if sections is None:
            sections = {"image": dict(IMAGE_MODELS)} if server.name == "image" else {}
        settings = Settings(output_dir=str(tmp_path / "out"), sections=sections, **overrides)
        llm = LLMClient(module=fake_litellm)
        inputs = InputResolver(settings)
        models = ModelRegistry(settings, llm, server, environ=environ or {})
        return AppContext(server, settings, llm, models, inputs,
                          OutputManager(settings, server.name))
    return build


@pytest.fixture
def ctx(make_ctx):
    return make_ctx()


@pytest.fixture
def photo(tmp_path):
    path = tmp_path / "photo.png"
    path.write_bytes(png_bytes((64, 48), "blue"))
    return path


@pytest.fixture
def mask_file(tmp_path):
    """Left half white (edit), right half black (keep)."""
    img = Image.new("L", (64, 48), 0)
    img.paste(255, (0, 0, 32, 48))
    path = tmp_path / "mask.png"
    img.save(path)
    return path

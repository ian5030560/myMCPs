import subprocess
import sys

import pytest

from mymcps.core.config import ModelSpec, ProviderSpec, Settings
from mymcps.core.errors import AuthError, ProviderError, RateLimitError
from mymcps.core.models import ModelRegistry
from mymcps.core.spec import Purpose, ServerSpec

DEMO = ServerSpec("demo", purposes=(Purpose("main", "a demo job"),))


def resolved(llm, model="openai/gpt-image-1", provider=None, **spec):
    settings = Settings(
        providers={"p": provider} if provider else {},
        models={"m": ModelSpec(model=model, provider="p" if provider else None, **spec)})
    return ModelRegistry(settings, llm, DEMO).resolve_model("m")


async def test_call_kwargs_are_forwarded(llm, fake_litellm):
    m = resolved(llm, provider=ProviderSpec(api_base="http://x"), extra={"timeout": 3})
    out = await llm.generate_image(m, "a cat", n=2)
    name, kw = fake_litellm.calls[0]
    assert out == {"ok": "aimage_generation"} and name == "aimage_generation"
    assert kw == {"model": "openai/gpt-image-1", "prompt": "a cat", "api_base": "http://x",
                  "timeout": 3, "n": 2}


async def test_other_calls(llm, fake_litellm):
    m = resolved(llm, "gemini/gemini-2.5-flash")
    await llm.complete(m, [{"role": "user", "content": "hi"}])
    await llm.edit_image(m, b"img", "edit")
    await llm.transcribe(m, b"aud")
    await llm.upload_file(m, b"file")
    assert [c[0] for c in fake_litellm.calls] == [
        "acompletion", "aimage_edit", "atranscription", "acreate_file"]
    assert fake_litellm.calls[3][1]["custom_llm_provider"] == "gemini"


class AuthenticationError(Exception):
    pass


class RateLimitError_(Exception):
    pass


RateLimitError_.__name__ = "RateLimitError"


async def test_auth_error_names_env_var(llm, fake_litellm):
    fake_litellm.raises = AuthenticationError("bad key")
    with pytest.raises(AuthError, match="GEMINI_API_KEY"):
        await llm.complete(resolved(llm, "gemini/x"), [])


async def test_auth_error_for_a_provider_with_its_own_key_points_at_the_provider(
        llm, fake_litellm):
    fake_litellm.raises = AuthenticationError("bad key")
    model = resolved(llm, "openai/x", provider=ProviderSpec(vendor="openai", api_key="k"))
    with pytest.raises(AuthError, match="provider `p`") as err:
        await llm.complete(model, [])
    assert "OPENAI_API_KEY" not in str(err.value)


async def test_rate_limit_and_unknown_errors(llm, fake_litellm):
    fake_litellm.raises = RateLimitError_("slow down")
    with pytest.raises(RateLimitError):
        await llm.complete(resolved(llm), [])
    fake_litellm.raises = ValueError("boom")
    with pytest.raises(ProviderError, match="boom"):
        await llm.complete(resolved(llm), [])


def test_importing_servers_does_not_load_litellm():
    code = ("import sys, mymcps.image.server, mymcps.video.server, "
            "mymcps.audio.server; sys.exit(1 if 'litellm' in sys.modules else 0)")
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0


def test_real_litellm_import_is_silent_on_stdout():
    code = ("from mymcps.core.llm import LLMClient; c = LLMClient(); "
            "m = 'gemini/gemini-2.5-flash'; c.get_vendor(m); c.table_entry(m)")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == ""

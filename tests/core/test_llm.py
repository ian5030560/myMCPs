import subprocess
import sys

import pytest

from conftest import completion_response, image_response, transcription_response
from mymcps.core.config import ModelSpec, ProviderSpec, Settings
from mymcps.core.errors import AuthError, ProviderError, RateLimitError
from mymcps.core.models import ModelRegistry
from mymcps.core.responses import GeneratedImage, Segment, Transcription, Word
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
    assert out == [] and name == "aimage_generation"
    assert kw == {"model": "openai/gpt-image-1", "prompt": "a cat", "api_base": "http://x",
                  "timeout": 3, "n": 2}


async def test_other_calls(llm, fake_litellm):
    m = resolved(llm, "gemini/gemini-2.5-flash")
    fake_litellm.queue = [completion_response("hello"), {}, {}, {"id": "files/abc"}]
    await llm.complete(m, [{"role": "user", "content": "hi"}])
    await llm.edit_image(m, b"img", "edit")
    await llm.transcribe(m, b"aud")
    await llm.upload_file(m, b"file")
    await llm.delete_file(m, "files/abc")
    assert [c[0] for c in fake_litellm.calls] == [
        "acompletion", "aimage_edit", "atranscription", "acreate_file", "afile_delete"]
    assert fake_litellm.calls[3][1]["custom_llm_provider"] == "gemini"
    assert fake_litellm.calls[4][1] == {"file_id": "files/abc", "custom_llm_provider": "gemini"}


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


@pytest.mark.parametrize("message, expected", [
    ("Rate limit exceeded. Please retry in 51s or upgrade", 51.0),
    ("quota used up, retry after 2.5 seconds", 2.5),
    ("slow down, retrying in 1500ms", 1.5),
    ("slow down", None),
])
async def test_a_rate_limit_carries_the_wait_the_provider_asked_for(
        llm, fake_litellm, message, expected):
    fake_litellm.raises = RateLimitError_(message)
    with pytest.raises(RateLimitError) as err:
        await llm.complete(resolved(llm), [])
    assert err.value.retry_after == expected


async def test_the_retry_after_header_wins_over_the_text(llm, fake_litellm):
    class Response:
        headers = {"retry-after": "12"}

    exc = RateLimitError_("please retry in 99s")
    exc.response = Response()
    fake_litellm.raises = exc
    with pytest.raises(RateLimitError) as err:
        await llm.complete(resolved(llm), [])
    assert err.value.retry_after == 12.0


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


class APIConnectionError(Exception):
    pass


TRACEBACK = ("litellm.APIConnectionError: GEMINI_API_KEY is not set\n"
             "Traceback (most recent call last):\n  File \"x.py\", line 1, in f\n    boom()")


async def test_a_missing_key_reported_as_a_connection_error_becomes_an_auth_error(
        llm, fake_litellm):
    fake_litellm.raises = APIConnectionError(TRACEBACK)
    with pytest.raises(AuthError, match="GEMINI_API_KEY environment variable") as err:
        await llm.generate_image(resolved(llm, "gemini/gemini-3.1-flash-image"), "a cat")
    assert "Traceback" not in str(err.value) and "x.py" not in str(err.value)


async def test_a_missing_key_names_the_providers_variable_when_it_has_one(llm, fake_litellm):
    fake_litellm.raises = APIConnectionError("LOCAL_KEY api_key is not set")
    model = resolved(llm, "openai/x", provider=ProviderSpec(vendor="openai", api_key="k"))
    with pytest.raises(AuthError, match="provider `p`"):
        await llm.complete(model, [])


async def test_other_errors_lose_an_embedded_traceback_too(llm, fake_litellm):
    fake_litellm.raises = APIConnectionError(
        "connection refused\nTraceback (most recent call last):\n  File \"x.py\"")
    with pytest.raises(ProviderError) as err:
        await llm.complete(resolved(llm), [])
    assert str(err.value).endswith("connection refused")
    assert not isinstance(err.value, AuthError)


# ── responses come back as plain values, whether LiteLLM gave objects or dicts ────────────

async def test_complete_returns_the_stripped_text(llm, fake_litellm):
    m = resolved(llm, "gemini/gemini-2.5-flash")
    fake_litellm.response = completion_response("  hi  ")
    assert await llm.complete(m, []) == "hi"
    fake_litellm.response = {"choices": [{"message": {"content": "from a dict"}}]}
    assert await llm.complete(m, []) == "from a dict"
    fake_litellm.response = completion_response(None)
    assert await llm.complete(m, []) == ""


async def test_complete_without_a_choice_is_a_provider_error(llm, fake_litellm):
    m = resolved(llm, "gemini/gemini-2.5-flash")
    for bad in ({"choices": []}, {}, None):
        fake_litellm.response = bad or {"ok": 1}
        with pytest.raises(ProviderError, match="returned no answer"):
            await llm.complete(m, [])


async def test_images_come_back_as_values(llm, fake_litellm):
    m = resolved(llm)
    fake_litellm.response = image_response(b"x", "https://img.test/a.png")
    assert await llm.generate_image(m, "p") == [
        GeneratedImage(b64="eA==", url=None), GeneratedImage(b64=None, url="https://img.test/a.png")]
    fake_litellm.response = {"data": [{"b64_json": "eA=="}]}
    assert await llm.edit_image(m, b"i", "p") == [GeneratedImage(b64="eA==")]


async def test_a_transcription_comes_back_as_a_value(llm, fake_litellm):
    m = resolved(llm, "gemini/gemini-2.5-flash")
    fake_litellm.response = transcription_response(
        " hello ", segments=[{"start": 1, "text": " a "}, {"start": None, "text": "x"}],
        words=[{"start": 0.5, "end": 1.0, "word": "hi"}, {"start": 2, "text": "yo"},
               {"start": 3, "word": " "}])
    assert await llm.transcribe(m, b"a") == Transcription(
        "hello", [Segment(1.0, "a")], [Word(0.5, 1.0, "hi"), Word(2.0, None, "yo")])
    fake_litellm.response = {"text": "plain"}
    assert await llm.transcribe(m, b"a") == Transcription("plain", [], [])


async def test_upload_returns_the_file_id_or_fails(llm, fake_litellm):
    m = resolved(llm, "gemini/gemini-2.5-flash")
    fake_litellm.response = {"id": "files/abc"}
    assert await llm.upload_file(m, b"f") == "files/abc"
    fake_litellm.response = {"name": "no id"}
    with pytest.raises(ProviderError, match="no file id"):
        await llm.upload_file(m, b"f")

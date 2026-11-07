from types import SimpleNamespace

import pytest
from mcp import Client

from conftest import completion_response
from mymcps.audio import limits

pytestmark = pytest.mark.ffmpeg


async def listen(server, **args):
    async with Client(server.mcp) as client:
        return await client.call_tool("listen_audio", args)


def text_of(result):
    return result.content[0].text


def names(fake_litellm):
    return [name for name, _ in fake_litellm.calls]


@pytest.fixture
def tiny_inline(monkeypatch):
    """Gemini takes 1 kB inline, so even a short recording goes through the Files API."""
    monkeypatch.setitem(limits.LIMITS, "gemini", limits.VendorLimits(
        inline_bytes=1000, max_seconds=9.5 * 3600, files_api=True))


UPLOADED = SimpleNamespace(id="files/abc123")


async def test_audio_over_the_inline_limit_is_uploaded_then_asked_then_deleted(
        server, fake_litellm, describe, tone, tiny_inline):
    fake_litellm.queue = [UPLOADED, completion_response("A tone."), {"deleted": True}]
    result = await listen(server, path=str(tone), prompt="What is it?")
    assert not result.is_error and text_of(result) == "A tone."
    assert names(fake_litellm) == ["acreate_file", "acompletion", "afile_delete"]
    # the whole compressed recording was uploaded, not split
    _, duration = describe(fake_litellm.uploads[0])
    assert 5.5 < duration < 6.5
    content = fake_litellm.calls[1][1]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "What is it?"}
    assert content[1] == {"type": "file",
                          "file": {"file_id": "files/abc123", "format": "audio/mpeg"}}
    deleted = fake_litellm.calls[2][1]
    assert deleted["file_id"] == "files/abc123" and deleted["custom_llm_provider"] == "gemini"


async def test_the_upload_is_deleted_when_the_question_fails(
        server, fake_litellm, tone, tiny_inline):
    fake_litellm.queue = [UPLOADED, RuntimeError("boom"), {"deleted": True}]
    result = await listen(server, path=str(tone), prompt="?")
    assert result.is_error and "boom" in text_of(result)
    assert names(fake_litellm) == ["acreate_file", "acompletion", "afile_delete"]


async def test_a_failed_delete_does_not_lose_the_answer(
        server, fake_litellm, tone, tiny_inline):
    fake_litellm.queue = [UPLOADED, completion_response("A tone."),
                          RuntimeError("cannot delete")]
    result = await listen(server, path=str(tone), prompt="?")
    assert not result.is_error and text_of(result) == "A tone."
    assert names(fake_litellm)[-1] == "afile_delete"


async def test_nothing_is_deleted_when_the_upload_failed(
        server, fake_litellm, tone, tiny_inline):
    fake_litellm.queue = [RuntimeError("no upload")]
    result = await listen(server, path=str(tone), prompt="?")
    assert result.is_error and "no upload" in text_of(result)
    assert names(fake_litellm) == ["acreate_file"]


async def test_an_upload_without_an_id_is_an_error(server, fake_litellm, tone, tiny_inline):
    fake_litellm.queue = [SimpleNamespace(id=None)]
    result = await listen(server, path=str(tone), prompt="?")
    assert result.is_error and "no file id" in text_of(result)
    assert names(fake_litellm) == ["acreate_file"]


async def test_audio_within_the_inline_limit_is_not_uploaded(server, fake_litellm, tone):
    fake_litellm.response = completion_response("ok")
    await listen(server, path=str(tone), prompt="?")
    assert names(fake_litellm) == ["acompletion"]


async def test_a_vendor_without_a_files_api_refuses_oversized_audio(
        server, fake_litellm, tone, monkeypatch):
    monkeypatch.setitem(limits.LIMITS, "gemini", limits.VendorLimits(inline_bytes=1000))
    result = await listen(server, path=str(tone), prompt="?")
    assert result.is_error and "start" in text_of(result)
    assert fake_litellm.calls == []


# ── the duration cap ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def three_second_cap(monkeypatch):
    monkeypatch.setitem(limits.LIMITS, "gemini", limits.VendorLimits(max_seconds=3.0))


async def test_a_recording_over_the_cap_names_two_ways_forward(
        server, fake_litellm, tone, three_second_cap, workdir):
    result = await listen(server, path=str(tone), prompt="?")       # 6 s
    message = text_of(result)
    assert result.is_error
    assert "`start` and `end`" in message and "`transcribe_audio`" in message
    assert "prompt" in message
    assert fake_litellm.calls == []
    assert not list(workdir.glob("*"))


async def test_the_cap_applies_to_the_range_asked_for(
        server, fake_litellm, tone, three_second_cap):
    fake_litellm.response = completion_response("ok")
    result = await listen(server, path=str(tone), prompt="?", start=3)      # 3 s: allowed
    assert not result.is_error
    result = await listen(server, path=str(tone), prompt="?", start=2)      # 4 s: too long
    assert result.is_error and "transcribe_audio" in text_of(result)


async def test_the_cap_is_checked_before_compressing(
        server, fake_litellm, tone, three_second_cap, monkeypatch):
    async def fail(*args, **kwargs):
        raise AssertionError("compression should not start")
    monkeypatch.setattr(server.ctx.ffmpeg, "extract_audio", fail)
    result = await listen(server, path=str(tone), prompt="?")
    assert result.is_error and "transcribe_audio" in text_of(result)


async def test_a_vendor_without_a_cap_is_never_refused_for_length(
        server, fake_litellm, tone):
    fake_litellm.response = completion_response("ok")
    result = await listen(server, path=str(tone), prompt="?", model="mistral/voxtral-small-latest")
    assert not result.is_error

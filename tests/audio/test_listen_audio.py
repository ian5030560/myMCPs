import base64

import pytest
from mcp import Client

from conftest import completion_response
from mymcps.audio.server import AudioServer

pytestmark = pytest.mark.ffmpeg


async def listen(server, **args):
    async with Client(server.mcp) as client:
        return await client.call_tool("listen_audio", args)


def text_of(result):
    return result.content[0].text


def sent_parts(fake_litellm):
    """(the text part, the audio part) of the one message the model received."""
    _, kw = fake_litellm.calls[0]
    content = kw["messages"][0]["content"]
    return content[0], content[1]


def sent_audio(fake_litellm) -> bytes:
    return base64.b64decode(sent_parts(fake_litellm)[1]["input_audio"]["data"])


async def test_returns_the_answer(server, fake_litellm, tone):
    fake_litellm.response = completion_response("  A steady tone.  ")
    result = await listen(server, path=str(tone), prompt="What do you hear?")
    assert not result.is_error and text_of(result) == "A steady tone."


async def test_sends_the_prompt_and_the_whole_compressed_recording(
        server, fake_litellm, describe, tone):
    fake_litellm.response = completion_response("ok")
    await listen(server, path=str(tone), prompt="What do you hear?")
    assert [name for name, _ in fake_litellm.calls] == ["acompletion"]
    assert fake_litellm.calls[0][1]["model"] == "gemini/gemini-2.5-flash"
    text, audio = sent_parts(fake_litellm)
    assert text == {"type": "text", "text": "What do you hear?"}
    assert audio["input_audio"]["format"] == "mp3"
    line, duration = describe(sent_audio(fake_litellm))
    assert "16000 Hz" in line and "mono" in line and "32 kb/s" in line
    assert 5.5 < duration < 6.5


async def test_start_and_end_limit_the_audio_sent(server, fake_litellm, describe, tone):
    fake_litellm.response = completion_response("ok")
    await listen(server, path=str(tone), prompt="?", start=1, end="00:03")
    _, duration = describe(sent_audio(fake_litellm))
    assert 1.5 < duration < 2.5


async def test_the_model_argument_wins(server, fake_litellm, tone):
    fake_litellm.response = completion_response("ok")
    await listen(server, path=str(tone), prompt="?", model="gemini/gemini-2.5-pro")
    assert fake_litellm.calls[0][1]["model"] == "gemini/gemini-2.5-pro"


async def test_the_tool_has_no_language_or_output_argument(server):
    async with Client(server.mcp) as client:
        tool = next(t for t in (await client.list_tools()).tools if t.name == "listen_audio")
    assert set(tool.input_schema["properties"]) == {
        "path", "prompt", "start", "end", "timestamps", "model"}


# ── timestamps ───────────────────────────────────────────────────────────────────────────

async def test_timestamps_asks_for_the_hh_mm_ss_form(server, fake_litellm, tone):
    fake_litellm.response = completion_response("At [00:00:02] a tone.")
    await listen(server, path=str(tone), prompt="Describe", timestamps=True)
    text, _ = sent_parts(fake_litellm)
    assert text["text"].startswith("Describe") and "[hh:mm:ss]" in text["text"]


async def test_prompt_is_unchanged_without_timestamps(server, fake_litellm, tone):
    fake_litellm.response = completion_response("ok")
    await listen(server, path=str(tone), prompt="Describe")
    assert sent_parts(fake_litellm)[0]["text"] == "Describe"


async def test_cited_times_are_moved_onto_the_original_recording(server, fake_litellm, tone):
    fake_litellm.response = completion_response("Starts at [00:02], ends at [00:01:05].")
    result = await listen(server, path=str(tone), prompt="?", start="00:03", timestamps=True)
    assert text_of(result) == "Starts at [00:00:05], ends at [00:01:08]."


async def test_times_are_left_alone_without_the_option(server, fake_litellm, tone):
    fake_litellm.response = completion_response("See [00:02].")
    result = await listen(server, path=str(tone), prompt="?", start=3)
    assert text_of(result) == "See [00:02]."


async def test_an_answer_without_times_is_an_error_when_they_were_requested(
        server, fake_litellm, tone):
    fake_litellm.response = completion_response("A tone, no times.")
    result = await listen(server, path=str(tone), prompt="?", timestamps=True)
    assert result.is_error and "no timestamps" in text_of(result)


# ── everything that can be wrong fails before the model is called ────────────────────────

async def test_a_missing_file(server, fake_litellm, tmp_path):
    result = await listen(server, path=str(tmp_path / "nope.mp3"), prompt="?")
    assert result.is_error and "not found" in text_of(result).lower()
    assert fake_litellm.calls == []


async def test_a_file_without_an_audio_stream(server, fake_litellm, silent_video):
    result = await listen(server, path=str(silent_video), prompt="?")
    assert result.is_error and "no audio" in text_of(result)
    assert fake_litellm.calls == []


async def test_a_bad_range(server, fake_litellm, tone):
    result = await listen(server, path=str(tone), prompt="?", start=4, end=2)
    assert result.is_error and "before" in text_of(result)
    assert fake_litellm.calls == []


# ── configuration ────────────────────────────────────────────────────────────────────────

async def test_an_unconfigured_purpose_names_the_setting(make_ctx, ffmpeg, fake_litellm, tone):
    server = AudioServer(make_ctx(server=AudioServer.spec, sections={}, ffmpeg=ffmpeg))
    result = await listen(server, path=str(tone), prompt="?")
    assert result.is_error and "listen_model" in text_of(result)
    assert fake_litellm.calls == []


async def test_a_model_that_cannot_hear_audio_is_named(server, fake_litellm, tone):
    result = await listen(server, path=str(tone), prompt="?", model="openai/gpt-4o")
    assert result.is_error and "gpt-4o" in text_of(result) and "listen_model" in text_of(result)
    assert fake_litellm.calls == []


async def test_a_transcription_model_cannot_listen(server, fake_litellm, tone):
    result = await listen(server, path=str(tone), prompt="?", model="openai/whisper-1")
    assert result.is_error and "whisper-1" in text_of(result)
    assert fake_litellm.calls == []


async def test_a_model_the_table_does_not_know_is_tried(server, fake_litellm, tone):
    fake_litellm.response = completion_response("ok")
    result = await listen(server, path=str(tone), prompt="?", model="gemini/brand-new")
    assert not result.is_error and len(fake_litellm.calls) == 1


@pytest.mark.parametrize("response", [completion_response(None), completion_response("  "),
                                      {"unexpected": True}])
async def test_an_empty_or_malformed_answer_is_an_error(server, fake_litellm, tone, response):
    fake_litellm.response = response
    result = await listen(server, path=str(tone), prompt="?")
    assert result.is_error


async def test_no_temporary_files_remain(server, fake_litellm, tone, workdir):
    fake_litellm.response = completion_response("ok")
    await listen(server, path=str(tone), prompt="?")
    fake_litellm.raises = RuntimeError("boom")
    result = await listen(server, path=str(tone), prompt="?")
    assert result.is_error and "boom" in text_of(result)
    await listen(server, path=str(tone), prompt="?", start=5, end=1)
    assert not list(workdir.glob("*"))

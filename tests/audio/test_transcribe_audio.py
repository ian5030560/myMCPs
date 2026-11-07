import sys

import httpx
import pytest
import respx
from mcp import Client

from conftest import transcription_response
from mymcps.audio.server import AudioServer

pytestmark = pytest.mark.ffmpeg


async def transcribe(server, **args):
    async with Client(server.mcp) as client:
        return await client.call_tool("transcribe_audio", args)


def text_of(result):
    return result.content[0].text


async def test_the_tools_are_listed(server):
    async with Client(server.mcp) as client:
        names = {t.name for t in (await client.list_tools()).tools}
    assert names == {"list_models", "transcribe_audio", "listen_audio"}


async def test_returns_the_transcript(server, fake_litellm, tone):
    fake_litellm.response = transcription_response("  hello there  ")
    result = await transcribe(server, path=str(tone))
    assert not result.is_error
    assert text_of(result) == "hello there"


async def test_a_short_recording_is_one_request_with_the_configured_model(
        server, fake_litellm, tone):
    await transcribe(server, path=str(tone))
    assert [name for name, _ in fake_litellm.calls] == ["atranscription"]
    assert fake_litellm.calls[0][1]["model"] == "openai/whisper-1"


async def test_the_model_argument_wins(server, fake_litellm, tone):
    await transcribe(server, path=str(tone), model="openai/whisper-1")
    assert fake_litellm.calls[0][1]["model"] == "openai/whisper-1"


async def test_sends_mono_16khz_32kbps_mp3(server, fake_litellm, describe, tone):
    await transcribe(server, path=str(tone))
    line, duration = describe(fake_litellm.transcriptions[0])
    assert line.split("Audio:")[1].startswith(" mp3")
    assert "16000 Hz" in line and "mono" in line and "32 kb/s" in line
    assert 5.5 < duration < 6.5


async def test_start_and_end_limit_the_audio_sent(server, fake_litellm, describe, tone):
    await transcribe(server, path=str(tone), start="00:02", end=4)
    _, duration = describe(fake_litellm.transcriptions[0])
    assert 1.5 < duration < 2.5


async def test_end_past_the_recording_means_the_end(server, fake_litellm, describe, tone):
    result = await transcribe(server, path=str(tone), start=3, end="1:00:00")
    assert not result.is_error
    _, duration = describe(fake_litellm.transcriptions[0])
    assert 2.5 < duration < 3.5


async def test_audio_is_taken_from_a_video(server, fake_litellm, run_ffmpeg, tmp_path):
    video = tmp_path / "media" / "clip.mp4"
    video.parent.mkdir()
    run_ffmpeg("-f", "lavfi", "-i", "testsrc=duration=3:size=64x48:rate=5",
               "-f", "lavfi", "-i", "sine=duration=3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-shortest", str(video))
    result = await transcribe(server, path=str(video))
    assert not result.is_error and len(fake_litellm.transcriptions) == 1


@respx.mock
async def test_a_url_is_downloaded_and_cleaned_up(server, fake_litellm, tone, workdir):
    respx.get("https://example.com/talk.wav").mock(
        return_value=httpx.Response(200, content=tone.read_bytes()))
    result = await transcribe(server, path="https://example.com/talk.wav")
    assert not result.is_error and len(fake_litellm.transcriptions) == 1
    assert not list(workdir.glob("*"))


# ── everything that can be wrong with the input fails before the model is called ─────────────

async def test_a_missing_file(server, fake_litellm, tmp_path):
    result = await transcribe(server, path=str(tmp_path / "nope.mp3"))
    assert result.is_error and "not found" in text_of(result).lower()
    assert fake_litellm.calls == []


async def test_a_file_that_is_not_media(server, fake_litellm, tmp_path):
    text = tmp_path / "notes.mp3"
    text.write_text("not audio")
    result = await transcribe(server, path=str(text))
    assert result.is_error and "notes.mp3" in text_of(result)
    assert fake_litellm.calls == []


async def test_a_file_without_an_audio_stream(server, fake_litellm, silent_video):
    result = await transcribe(server, path=str(silent_video))
    assert result.is_error and "no audio" in text_of(result)
    assert fake_litellm.calls == []


@pytest.mark.parametrize("args,message", [
    ({"start": 4, "end": 2}, "before"),
    ({"start": 3, "end": 3}, "before"),
    ({"start": 60}, "past the end"),
    ({"start": -1}, "negative"),
    ({"start": "soon"}, "Invalid timestamp"),
    ({"end": "1:2:3:4"}, "Invalid timestamp"),
])
async def test_a_bad_range(server, fake_litellm, tone, args, message):
    result = await transcribe(server, path=str(tone), **args)
    assert result.is_error and message in text_of(result)
    assert fake_litellm.calls == []


# ── configuration ────────────────────────────────────────────────────────────────────────

async def test_an_unconfigured_purpose_names_the_setting(make_ctx, ffmpeg, fake_litellm, tone):
    server = AudioServer(make_ctx(server=AudioServer.spec, sections={}, ffmpeg=ffmpeg))
    result = await transcribe(server, path=str(tone))
    assert result.is_error and "transcribe_model" in text_of(result)
    assert fake_litellm.calls == []


async def test_a_model_that_cannot_transcribe_is_named(server, fake_litellm, tone):
    result = await transcribe(server, path=str(tone), model="openai/gpt-3.5-turbo")
    assert result.is_error and "gpt-3.5-turbo" in text_of(result)
    assert "transcribe_model" in text_of(result)
    assert fake_litellm.calls == []


async def test_a_model_the_table_does_not_know_is_tried(server, fake_litellm, tone):
    result = await transcribe(server, path=str(tone), model="openai/brand-new-model")
    assert not result.is_error and len(fake_litellm.calls) == 1


async def test_missing_ffmpeg_points_to_the_audio_extra(make_ctx, fake_litellm, tone, monkeypatch):
    monkeypatch.setitem(sys.modules, "imageio_ffmpeg", None)        # makes the import fail
    server = AudioServer(make_ctx(server=AudioServer.spec))
    result = await transcribe(server, path=str(tone))
    assert result.is_error and "mymcps[audio]" in text_of(result)
    assert fake_litellm.calls == []


# ── temporary files ──────────────────────────────────────────────────────────────────────

async def test_no_temporary_files_remain_after_success(server, tone, workdir):
    await transcribe(server, path=str(tone))
    assert not list(workdir.glob("*"))


async def test_no_temporary_files_remain_after_a_model_error(
        server, fake_litellm, tone, workdir):
    fake_litellm.raises = RuntimeError("boom")
    result = await transcribe(server, path=str(tone))
    assert result.is_error and "boom" in text_of(result)
    assert not list(workdir.glob("*"))


async def test_no_temporary_files_remain_after_a_validation_error(server, tone, workdir):
    await transcribe(server, path=str(tone), start=4, end=2)
    assert not list(workdir.glob("*"))

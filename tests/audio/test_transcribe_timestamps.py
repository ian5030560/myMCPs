from types import SimpleNamespace

import pytest
from mcp import Client

from conftest import transcription_response

pytestmark = pytest.mark.ffmpeg

SEGMENTS = [{"start": 0.0, "text": " Hello."}, {"start": 61.4, "text": " Second one. "},
            {"start": 3725.0, "text": ""}, {"start": 3725.0, "text": "Late."}]


async def transcribe(server, **args):
    async with Client(server.mcp) as client:
        return await client.call_tool("transcribe_audio", args)


def text_of(result):
    return result.content[0].text


async def test_language_is_passed_to_the_model(server, fake_litellm, tone):
    await transcribe(server, path=str(tone), language="zh")
    assert fake_litellm.calls[0][1]["language"] == "zh"


async def test_nothing_extra_is_sent_unless_asked_for(server, fake_litellm, tone):
    await transcribe(server, path=str(tone))
    assert "language" not in fake_litellm.calls[0][1]
    assert "response_format" not in fake_litellm.calls[0][1]


async def test_timestamps_lead_each_segment(server, fake_litellm, tone):
    fake_litellm.response = transcription_response("ignored", SEGMENTS)
    result = await transcribe(server, path=str(tone), timestamps=True)
    assert not result.is_error
    assert text_of(result).splitlines() == [
        "[00:00:00] Hello.", "[00:01:01] Second one.", "[01:02:05] Late."]
    assert fake_litellm.calls[0][1]["response_format"] == "verbose_json"


@pytest.mark.parametrize("start,shown", [
    (0.4, "00:00:00"), (0.5, "00:00:01"), (61.6, "00:01:02"), (59.5, "00:01:00"),
    (3599.6, "01:00:00")])
async def test_times_are_rounded_to_the_nearest_second(server, fake_litellm, tone, start, shown):
    fake_litellm.response = transcription_response("x", [{"start": start, "text": "Hi"}])
    result = await transcribe(server, path=str(tone), timestamps=True)
    assert text_of(result) == f"[{shown}] Hi"


async def test_timestamps_count_from_the_original_recording(server, fake_litellm, tone):
    fake_litellm.response = transcription_response(
        "x", [{"start": 0.5, "text": "Hi"}, {"start": 2.0, "text": "There"}])
    result = await transcribe(server, path=str(tone), start="00:03", timestamps=True)
    assert text_of(result).splitlines() == ["[00:00:04] Hi", "[00:00:05] There"]


async def test_segments_may_be_objects(server, fake_litellm, tone):
    fake_litellm.response = transcription_response(
        "x", [SimpleNamespace(start=7.0, text="Object segment")])
    result = await transcribe(server, path=str(tone), timestamps=True)
    assert text_of(result) == "[00:00:07] Object segment"


@pytest.mark.parametrize("segments", [None, [], [{"start": 1.0, "text": "  "}]])
async def test_timestamps_without_times_from_the_model_is_an_error(
        server, fake_litellm, tone, segments):
    fake_litellm.response = transcription_response("plain text only", segments)
    result = await transcribe(server, path=str(tone), timestamps=True)
    assert result.is_error and "no timestamps" in text_of(result)


async def test_a_model_that_returns_no_times_is_named(server, fake_litellm, tone):
    fake_litellm.response = transcription_response("plain text only")
    result = await transcribe(server, path=str(tone), timestamps=True,
                              model="openai/gpt-4o-transcribe")
    assert result.is_error and "gpt-4o-transcribe" in text_of(result)


# ── how each vendor is asked, and models that time every word ────────────────────────────

async def test_openai_is_asked_for_verbose_json(server, fake_litellm, tone):
    fake_litellm.response = transcription_response("x", [{"start": 1.0, "text": "Hi"}])
    await transcribe(server, path=str(tone), timestamps=True)
    kw = fake_litellm.calls[0][1]
    assert kw["response_format"] == "verbose_json" and "timestamp_granularities" not in kw


def word(start, end, text):
    return {"word": text, "start": start, "end": end}


async def test_gemini_is_asked_for_word_times(server, fake_litellm, tone):
    fake_litellm.response = transcription_response("x", words=[word(0.0, 0.4, "Hi")])
    result = await transcribe(server, path=str(tone), timestamps=True,
                              model="gemini/gemini-3.5-transcribe")
    kw = fake_litellm.calls[0][1]
    assert kw["timestamp_granularities"] == ["word"] and "response_format" not in kw
    assert text_of(result) == "[00:00:00] Hi"


async def test_words_are_grouped_into_lines_at_pauses(server, fake_litellm, tone):
    fake_litellm.response = transcription_response("x", words=[
        word(0.0, 0.4, "Good"), word(0.5, 0.9, "morning"),
        word(1.6, 2.0, "everyone"),                                # 0.7 s pause: same line
        word(2.81, 3.1, "Let's"), word(3.2, 3.5, "begin"),         # 0.81 s pause: new line
    ])
    result = await transcribe(server, path=str(tone), timestamps=True,
                              model="gemini/gemini-3.5-transcribe")
    assert text_of(result).splitlines() == [
        "[00:00:00] Good morning everyone", "[00:00:03] Let's begin"]


async def test_a_line_never_runs_past_ten_seconds(server, fake_litellm, tone):
    # a word every half second with no pause: 25 words = 12 s of continuous speech
    fake_litellm.response = transcription_response("x", words=[
        word(i * 0.5, i * 0.5 + 0.4, f"w{i}") for i in range(25)])
    result = await transcribe(server, path=str(tone), timestamps=True,
                              model="gemini/gemini-3.5-transcribe")
    lines = text_of(result).splitlines()
    assert lines[0].startswith("[00:00:00] w0 w1") and lines[0].endswith("w19")
    assert lines[1].startswith("[00:00:10] w20") and lines[1].endswith("w24")


async def test_words_without_an_end_time_are_split_by_length_only(server, fake_litellm, tone):
    fake_litellm.response = transcription_response("x", words=[
        {"word": "a", "start": 0.0}, {"word": "b", "start": 5.0}, {"word": "c", "start": 10.0}])
    result = await transcribe(server, path=str(tone), timestamps=True,
                              model="gemini/gemini-3.5-transcribe")
    assert text_of(result).splitlines() == ["[00:00:00] a b", "[00:00:10] c"]


async def test_chinese_words_are_joined_without_spaces(server, fake_litellm, tone):
    fake_litellm.response = transcription_response("x", words=[
        word(0.0, 0.3, "大家"), word(0.3, 0.6, "好"), word(0.7, 1.0, "OK"), word(1.0, 1.2, "吧")])
    result = await transcribe(server, path=str(tone), timestamps=True,
                              model="gemini/gemini-3.5-transcribe")
    assert text_of(result) == "[00:00:00] 大家好 OK 吧"


async def test_segments_are_preferred_when_both_come_back(server, fake_litellm, tone):
    fake_litellm.response = transcription_response(
        "x", [{"start": 2.0, "text": "Whole sentence."}], words=[word(0.0, 0.4, "Hi")])
    result = await transcribe(server, path=str(tone), timestamps=True)
    assert text_of(result) == "[00:00:02] Whole sentence."

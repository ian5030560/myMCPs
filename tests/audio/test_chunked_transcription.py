import pytest
from mcp import Client

from conftest import transcription_response

pytestmark = pytest.mark.ffmpeg

# 25 s of audio, at most 9.5 s per chunk, aiming at 8.55 s: the cuts land at 8.55 s (inside the
# silence at 8-9 s) and 17.1 s (inside 17-18 s), giving chunks of 8.55, 8.55 and 7.9 s.
CUTS = (8.55, 17.1)


async def transcribe(server, **args):
    async with Client(server.mcp) as client:
        return await client.call_tool("transcribe_audio", args)


def text_of(result):
    return result.content[0].text


def three_chunks(fake_litellm):
    fake_litellm.queue = [
        transcription_response("One", [{"start": 0.0, "text": "One"}]),
        transcription_response("Two", [{"start": 1.0, "text": "Two"}]),
        transcription_response("Three", [{"start": 0.5, "text": "Three"}]),
    ]


async def test_a_recording_over_the_limit_is_sent_in_chunks(
        server, fake_litellm, describe, long_audio, small_requests):
    three_chunks(fake_litellm)
    result = await transcribe(server, path=str(long_audio))
    assert not result.is_error and text_of(result) == "One\nTwo\nThree"
    assert len(fake_litellm.transcriptions) == 3
    durations = [describe(data)[1] for data in fake_litellm.transcriptions]
    assert durations == pytest.approx([8.55, 8.55, 7.9], abs=0.25)
    assert all(len(data) <= 40_000 for data in fake_litellm.transcriptions)


async def test_chunks_are_cut_inside_the_silences(
        server, fake_litellm, describe, long_audio, small_requests, ffmpeg):
    """Both ends of every cut are quiet: the first chunk ends in the 8-9 s silence."""
    three_chunks(fake_litellm)
    await transcribe(server, path=str(long_audio))
    first = fake_litellm.transcriptions[0]
    # the last half second of the first chunk is silent: it is the tail of the 8-9 s gap
    path = ffmpeg._workdir.parent / "first.mp3"
    path.write_bytes(first)
    import subprocess
    out = subprocess.run([ffmpeg._exe, "-hide_banner", "-nostats", "-sseof", "-0.3", "-i",
                          str(path), "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    max_volume = float(out.split("max_volume:")[1].split("dB")[0])
    assert max_volume < -30


async def test_times_are_moved_onto_the_original_recording(
        server, fake_litellm, long_audio, small_requests):
    three_chunks(fake_litellm)
    result = await transcribe(server, path=str(long_audio), timestamps=True)
    assert text_of(result).splitlines() == [
        "[00:00:00] One", "[00:00:10] Two", "[00:00:18] Three"]


async def test_times_follow_start_when_chunking(server, fake_litellm, long_audio, small_requests):
    three_chunks(fake_litellm)
    result = await transcribe(server, path=str(long_audio), start=5, timestamps=True)
    assert len(fake_litellm.transcriptions) == 3        # 20 s of audio is still over the limit
    lines = text_of(result).splitlines()
    assert lines[0] == "[00:00:05] One"
    assert lines[1].startswith("[00:00:") and lines[1].endswith("Two")


async def test_without_silence_the_cut_is_at_the_target(
        server, fake_litellm, describe, long_tone, small_requests):
    three_chunks(fake_litellm)
    await transcribe(server, path=str(long_tone))
    durations = [describe(data)[1] for data in fake_litellm.transcriptions]
    assert durations == pytest.approx([8.55, 8.55, 7.9], abs=0.25)


async def test_a_recording_that_fits_is_not_split(server, fake_litellm, tone, small_requests):
    await transcribe(server, path=str(tone))        # 6 s: 24 kB
    assert len(fake_litellm.transcriptions) == 1


async def test_a_duration_limit_splits_a_recording_that_fits_the_size_limit(
        server, fake_litellm, describe, long_audio, monkeypatch):
    """25 s is far below the size limit, but one request takes at most 10 s of audio."""
    from mymcps.audio import limits
    monkeypatch.setitem(limits.LIMITS, "openai", limits.VendorLimits(
        transcribe_bytes=25_000_000, transcribe_seconds=10))
    three_chunks(fake_litellm)
    result = await transcribe(server, path=str(long_audio))
    assert not result.is_error and len(fake_litellm.transcriptions) == 3
    durations = [describe(data)[1] for data in fake_litellm.transcriptions]
    assert durations == pytest.approx([8.55, 8.55, 7.9], abs=0.25)
    assert all(d <= 10 for d in durations)


async def test_a_recording_within_the_duration_limit_is_not_split(
        server, fake_litellm, tone, monkeypatch):
    from mymcps.audio import limits
    monkeypatch.setitem(limits.LIMITS, "openai", limits.VendorLimits(transcribe_seconds=10))
    await transcribe(server, path=str(tone))            # 6 s
    assert len(fake_litellm.transcriptions) == 1


async def test_asking_for_times_uses_the_shorter_duration_limit(
        server, fake_litellm, long_audio, monkeypatch):
    """Gemini takes 1 hour per request, but only 30 minutes when word times are asked for."""
    from mymcps.audio import limits
    monkeypatch.setitem(limits.LIMITS, "openai", limits.VendorLimits(
        transcribe_seconds=100, timed_transcribe_seconds=10))
    await transcribe(server, path=str(long_audio))              # 25 s, no times: one request
    assert len(fake_litellm.transcriptions) == 1
    three_chunks(fake_litellm)
    await transcribe(server, path=str(long_audio), timestamps=True)
    assert len(fake_litellm.transcriptions) == 1 + 3


def test_gemini_limits_follow_the_model_documentation():
    from mymcps.audio import limits
    gemini = limits.limits_for("gemini")
    assert gemini.transcribe_seconds == 3600
    assert gemini.timed_transcribe_seconds == 1800
    # 25 tokens a second against 98,304 input tokens: a full hour still fits
    assert gemini.transcribe_seconds * 25 < 98_304
    # the size limit alone (20 MB, 83 minutes) would let a chunk through that is too long
    assert gemini.transcribe_bytes / 4000 > gemini.transcribe_seconds


async def test_a_vendor_without_a_known_limit_is_never_split(
        server, fake_litellm, long_audio, small_requests):
    result = await transcribe(server, path=str(long_audio), model="mistral/voxtral-mini-latest")
    assert not result.is_error and len(fake_litellm.transcriptions) == 1


# ── a chunk the vendor rejects is reported, never dropped ────────────────────────────────

async def test_a_rejected_chunk_is_marked_where_it_is(
        server, fake_litellm, long_audio, small_requests):
    fake_litellm.queue = [transcription_response("One"),
                          RuntimeError("audio could not be decoded"),
                          transcription_response("Three")]
    result = await transcribe(server, path=str(long_audio))
    assert not result.is_error
    first, marker, last = text_of(result).splitlines()
    assert first == "One" and last == "Three"
    assert marker.startswith("[not transcribed 00:00:09-00:00:17:")
    assert "audio could not be decoded" in marker
    assert len(fake_litellm.transcriptions) == 3        # the other chunks were still sent


async def test_the_marker_takes_part_in_timestamps(
        server, fake_litellm, long_audio, small_requests):
    fake_litellm.queue = [
        transcription_response("One", [{"start": 0.0, "text": "One"}]),
        RuntimeError("nope"),
        transcription_response("Three", [{"start": 0.5, "text": "Three"}])]
    result = await transcribe(server, path=str(long_audio), timestamps=True)
    lines = text_of(result).splitlines()
    assert lines[0] == "[00:00:00] One"
    assert lines[1].startswith("[00:00:09] [not transcribed 00:00:09-00:00:17:")
    assert lines[2] == "[00:00:18] Three"


async def test_nothing_transcribed_is_an_error(server, fake_litellm, long_audio, small_requests):
    fake_litellm.queue = [RuntimeError("bad 1"), RuntimeError("bad 2"), RuntimeError("bad 3")]
    result = await transcribe(server, path=str(long_audio))
    assert result.is_error and "bad 1" in text_of(result)


async def test_a_bad_key_stops_at_the_first_chunk(
        server, fake_litellm, long_audio, small_requests):
    class AuthenticationError(Exception):
        pass

    fake_litellm.queue = [AuthenticationError("invalid key")]
    result = await transcribe(server, path=str(long_audio))
    assert result.is_error and "invalid key" in text_of(result)
    assert len(fake_litellm.calls) == 1


async def test_a_model_without_times_stops_at_the_first_chunk(
        server, fake_litellm, long_audio, small_requests):
    fake_litellm.queue = [transcription_response("plain text only")]
    result = await transcribe(server, path=str(long_audio), timestamps=True)
    assert result.is_error and "no timestamps" in text_of(result)
    assert len(fake_litellm.calls) == 1


# ── a rate limit is waited out ───────────────────────────────────────────────────────────

class RateLimitError(Exception):
    """LiteLLM's name for it: the client recognises the error by the class name."""


@pytest.fixture
def pauses(monkeypatch):
    """No real waiting: the seconds each pause was asked for are recorded."""
    waits: list[float] = []

    async def pause(seconds):
        waits.append(seconds)

    monkeypatch.setattr("mymcps.audio.transcriber._pause", pause)
    return waits


def limited(text="Rate limit exceeded. Please retry in 7s"):
    return RateLimitError(text)


async def test_a_rate_limited_chunk_is_sent_again_after_the_wait(
        server, fake_litellm, long_audio, small_requests, pauses):
    fake_litellm.queue = [transcription_response("One"), limited(),
                          transcription_response("Two"), transcription_response("Three")]
    result = await transcribe(server, path=str(long_audio))
    assert not result.is_error and text_of(result) == "One\nTwo\nThree"
    assert pauses == [8.0]                              # the 7 s asked for, and a second more
    assert len(fake_litellm.transcriptions) == 4        # the second chunk was sent twice


async def test_a_wait_the_provider_gives_no_hint_for_uses_a_default(
        server, fake_litellm, long_audio, small_requests, pauses):
    fake_litellm.queue = [transcription_response("One"), limited("slow down"),
                          transcription_response("Two"), transcription_response("Three")]
    await transcribe(server, path=str(long_audio))
    assert pauses == [31.0]


async def test_a_very_long_wait_is_capped(
        server, fake_litellm, long_audio, small_requests, pauses):
    fake_litellm.queue = [transcription_response("One"), limited("retry in 900s"),
                          transcription_response("Two"), transcription_response("Three")]
    await transcribe(server, path=str(long_audio))
    assert pauses == [121.0]


async def test_a_chunk_that_stays_limited_keeps_what_is_done_and_marks_the_rest(
        server, fake_litellm, long_audio, small_requests, pauses):
    fake_litellm.queue = [transcription_response("One")] + [limited()] * 6
    result = await transcribe(server, path=str(long_audio))
    assert not result.is_error
    first, marker, rest = text_of(result).splitlines()
    assert first == "One"
    assert marker.startswith("[not transcribed 00:00:09-00:00:17:") and "retry in 7s" in marker
    assert rest.startswith("[not transcribed 00:00:17-00:00:25: not sent")
    assert len(pauses) == 5                             # five waits, six tries, then it gives up
    assert len(fake_litellm.transcriptions) == 1 + 6    # nothing is sent after that


async def test_limited_from_the_start_is_an_error(
        server, fake_litellm, long_audio, small_requests, pauses):
    fake_litellm.queue = [limited()] * 6
    result = await transcribe(server, path=str(long_audio))
    assert result.is_error and "Rate limit" in text_of(result)


async def test_a_single_request_is_also_waited_for(server, fake_litellm, tone, pauses):
    fake_litellm.queue = [limited(), transcription_response("Done")]
    result = await transcribe(server, path=str(tone))
    assert not result.is_error and text_of(result) == "Done" and pauses == [8.0]


# ── temporary files ──────────────────────────────────────────────────────────────────────

async def test_no_temporary_files_remain_after_chunking(
        server, fake_litellm, long_audio, small_requests, workdir):
    three_chunks(fake_litellm)
    await transcribe(server, path=str(long_audio))
    assert not list(workdir.glob("*"))


async def test_no_temporary_files_remain_after_a_failure(
        server, fake_litellm, long_audio, small_requests, workdir):
    fake_litellm.queue = [transcription_response("One"), RuntimeError("x"),
                          RuntimeError("y")]
    await transcribe(server, path=str(long_audio))
    fake_litellm.queue = [RuntimeError("z")] * 3
    await transcribe(server, path=str(long_audio))
    assert not list(workdir.glob("*"))

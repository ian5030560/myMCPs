"""Fixtures shared by the audio tests: real ffmpeg, generated recordings, an audio server."""

import subprocess

import pytest

from mymcps.audio.server import AudioServer
from mymcps.core.ffmpeg import FFmpeg


@pytest.fixture
def ffmpeg(tmp_path):
    return FFmpeg.bundled(tmp_path / "work", extra="audio")


@pytest.fixture
def workdir(tmp_path):
    """Where the context's ffmpeg keeps its temporary files; must be empty after every call."""
    return tmp_path / "work"


@pytest.fixture
def server(make_ctx, ffmpeg):
    return AudioServer(make_ctx(server=AudioServer.spec, ffmpeg=ffmpeg))


@pytest.fixture
def run_ffmpeg(ffmpeg):
    def run(*args):
        return subprocess.run([ffmpeg._exe, "-hide_banner", "-y", *args], check=True,
                              capture_output=True, text=True)
    return run


@pytest.fixture
def tone(run_ffmpeg, tmp_path):
    """A 6 second 440 Hz tone as a stereo 44.1 kHz wav (nothing like what gets sent)."""
    path = tmp_path / "media" / "tone.wav"
    path.parent.mkdir()
    run_ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=6:sample_rate=44100",
               "-ac", "2", str(path))
    return path


@pytest.fixture
def silent_video(run_ffmpeg, tmp_path):
    path = tmp_path / "media" / "silent.mp4"
    path.parent.mkdir()
    run_ffmpeg("-f", "lavfi", "-i", "testsrc=duration=2:size=64x48:rate=5",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path))
    return path


@pytest.fixture
def describe(ffmpeg, tmp_path):
    """What ffmpeg says about audio that was sent: (the stream line, duration in seconds)."""
    def inspect(data: bytes):
        sent = tmp_path / "sent.mp3"
        sent.write_bytes(data)
        out = subprocess.run([ffmpeg._exe, "-hide_banner", "-i", str(sent)],
                             capture_output=True, text=True).stderr
        line = next(ln for ln in out.splitlines() if "Audio:" in ln)
        hh, mm, ss = out.split("Duration:")[1].split(",")[0].split(":")
        return line, int(hh) * 3600 + int(mm) * 60 + float(ss)
    return inspect


def _recording(run_ffmpeg, tmp_path, name, seconds, silences):
    path = tmp_path / "media" / name
    path.parent.mkdir(exist_ok=True)
    gaps = "+".join(f"between(t,{a},{b})" for a, b in silences)
    filters = ["-af", f"volume=enable='{gaps}':volume=0"] if silences else []
    run_ffmpeg("-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}:sample_rate=44100",
               *filters, str(path))
    return path


@pytest.fixture
def long_audio(run_ffmpeg, tmp_path):
    """25 seconds of tone with silences at 8-9 s and 17-18 s."""
    return _recording(run_ffmpeg, tmp_path, "long.wav", 25, [(8, 9), (17, 18)])


@pytest.fixture
def long_tone(run_ffmpeg, tmp_path):
    """25 seconds of tone without any silence."""
    return _recording(run_ffmpeg, tmp_path, "unbroken.wav", 25, [])


@pytest.fixture
def small_requests(monkeypatch):
    """OpenAI takes 40 kB per transcription request: 10 s of the compressed audio, so a
    25 s recording must be split into 3 chunks (the longest allowed is 9.5 s)."""
    from mymcps.audio import limits
    monkeypatch.setitem(limits.LIMITS, "openai", limits.VendorLimits(transcribe_bytes=40_000))

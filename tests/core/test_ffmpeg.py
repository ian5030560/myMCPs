import subprocess

import pytest

from mymcps.core.errors import FFmpegError
from mymcps.core.ffmpeg import FFmpeg


@pytest.mark.parametrize("value,expected", [
    (5, 5.0), ("12.5", 12.5), ("01:30", 90.0), ("1:01:01.5", 3661.5), ("00:00:02", 2.0)])
def test_parse_timestamp(value, expected):
    assert FFmpeg.parse_timestamp(value) == expected


@pytest.mark.parametrize("bad", ["abc", "1:2:3:4", "a:b"])
def test_parse_timestamp_invalid(bad):
    with pytest.raises(FFmpegError):
        FFmpeg.parse_timestamp(bad)


pytestmark_ffmpeg = pytest.mark.ffmpeg


@pytest.fixture(scope="module")
def ff(tmp_path_factory):
    return FFmpeg.bundled(tmp_path_factory.mktemp("work"))


@pytest.fixture(scope="module")
def clip(ff, tmp_path_factory):
    path = tmp_path_factory.mktemp("media") / "clip.mp4"
    subprocess.run(
        [ff._exe, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=duration=4:size=320x240:rate=10",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
        check=True)
    return path


@pytest.mark.ffmpeg
async def test_probe(ff, clip):
    info = await ff.probe(clip)
    assert 3.5 < info.duration < 4.5
    assert info.has_video and info.has_audio and (info.width, info.height) == (320, 240)


@pytest.mark.ffmpeg
async def test_probe_not_media(ff, tmp_path):
    bad = tmp_path / "x.mp4"
    bad.write_bytes(b"not media")
    with pytest.raises(FFmpegError):
        await ff.probe(bad)


@pytest.mark.ffmpeg
async def test_extract_frames_at_times_and_fps(ff, clip):
    frames = await ff.extract_frames(clip, times=[0.5, "00:00:02"], max_side=160)
    assert len(frames) == 2 and all(f.stat().st_size > 0 for f in frames)
    seq = await ff.extract_frames(clip, fps=1, start=1, end=3)
    assert 1 <= len(seq) <= 3


@pytest.mark.ffmpeg
async def test_extract_audio_cut_split(ff, clip):
    audio = await ff.extract_audio(clip, start=1, end=3)
    assert 1.5 < (await ff.probe(audio)).duration < 2.5
    assert not (await ff.probe(audio)).has_video
    cut = await ff.cut(clip, 1, 2)
    assert 0.5 < (await ff.probe(cut)).duration < 1.6
    parts = await ff.split(audio, 1)
    assert len(parts) >= 2


@pytest.mark.ffmpeg
async def test_compress(ff, clip):
    small = await ff.compress(clip, max_height=120)
    assert (await ff.probe(small)).height == 120

"""Turn a user-supplied recording into the small mono mp3 both audio tools send.

Everything that can fail on the input fails here, before any model is called, so a bad input
never costs money (ADR 0005).
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from mymcps.core.context import AppContext
from mymcps.core.errors import FFmpegError, InputError
from mymcps.core.ffmpeg import FFmpeg

BITRATE = "32k"
SAMPLE_RATE = 16000
BYTES_PER_SECOND = 32_000 // 8      # the compressed audio is constant bitrate


class RecordingTooLong(InputError):
    """The range asked for is longer than ``max_seconds``. A caller may reword the message."""

    def __init__(self, seconds: float, limit: float):
        super().__init__(
            f"The recording is {seconds / 3600:.1f} hours, over the {limit / 3600:.1f} hours "
            "one request takes. Use a shorter range with `start` and `end`.")
        self.seconds = seconds
        self.limit = limit


@dataclass
class PreparedAudio:
    path: Path          # the compressed mp3 (removed when the context exits)
    offset: float       # seconds into the original recording where this audio starts
    duration: float     # seconds of audio in `path`
    size: int           # bytes of `path`


@contextlib.asynccontextmanager
async def prepare(ctx: AppContext, source: str, start=None, end=None, *,
                  max_seconds: float | None = None) -> AsyncIterator[PreparedAudio]:
    """Resolve, validate, trim to ``start``/``end`` and compress ``source``.

    A range longer than ``max_seconds`` is refused with ``RecordingTooLong`` before anything
    is compressed.

    Temporary files (a download, the compressed audio) are removed on exit, also after errors.
    """
    first = _seconds(start, "start")
    last = _seconds(end, "end")
    async with await ctx.inputs.resolve(source) as media:
        ffmpeg = ctx.ffmpeg
        info = await _probe(ffmpeg, media.path)
        if not info.has_audio:
            raise InputError(f"{media.path.name} has no audio stream.")
        first = first or 0.0
        last = info.duration if last is None else min(last, info.duration)
        if first >= info.duration:
            raise InputError(
                f"`start` ({first:g} s) is at or past the end of the recording "
                f"({info.duration:g} s).")
        if first >= last:
            raise InputError(f"`start` ({first:g} s) must be before `end` ({last:g} s).")
        if max_seconds is not None and last - first > max_seconds:
            raise RecordingTooLong(last - first, max_seconds)
        compressed = await ffmpeg.extract_audio(
            media.path, start=first or None, end=None if last == info.duration else last,
            bitrate=BITRATE, sample_rate=SAMPLE_RATE)
        try:
            yield PreparedAudio(compressed, first, last - first, compressed.stat().st_size)
        finally:
            with contextlib.suppress(OSError):
                compressed.unlink()


async def _probe(ffmpeg: FFmpeg, path: Path):
    try:
        return await ffmpeg.probe(path)
    except FFmpegError as exc:
        raise InputError(f"{path.name} is not readable audio or video: {exc}") from exc


def _seconds(value, name: str) -> float | None:
    if value is None:
        return None
    try:
        seconds = FFmpeg.parse_timestamp(value)
    except FFmpegError as exc:
        raise InputError(f"`{name}`: {exc}") from exc
    if seconds < 0:
        raise InputError(f"`{name}` cannot be negative.")
    return seconds

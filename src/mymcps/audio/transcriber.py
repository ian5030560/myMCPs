"""Speech to text.

A recording that fits one request is sent whole. A longer one is cut into chunks at silence,
each chunk is transcribed, and the times are moved back onto the original recording (ADR 0005).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from pathlib import Path

from mymcps.core.abilities import TRANSCRIPTION
from mymcps.core.context import AppContext
from mymcps.core.errors import (
    FFmpegError,
    ModelError,
    ProviderError,
    RateLimitError,
    UnsupportedCapabilityError,
)
from mymcps.core.responses import field

from .limits import limits_for
from .planner import plan_chunks
from .prepare import BYTES_PER_SECOND, PreparedAudio, prepare
from .timestamps import Segment, Word, format_time, group_words, mark_segments

# A chunk is planned to fill this much of what one request carries, leaving room for headers.
SIZE_MARGIN = 0.95
# Where a cut is aimed at, as a share of the longest allowed chunk.
TARGET_SHARE = 0.9
# A rate limit is waited out: as long as the provider asks (capped), and a chunk is sent again at
# most this many times before it counts as failed.
RATE_LIMIT_RETRIES = 5
DEFAULT_WAIT = 30.0
MAX_WAIT = 120.0

log = logging.getLogger(__name__)


async def _pause(seconds: float) -> None:
    # A named function so tests can replace the wait without patching asyncio itself.
    await asyncio.sleep(seconds)


@dataclass
class _Chunk:
    path: Path
    start: float    # seconds into the prepared audio
    end: float


class Transcriber:
    def __init__(self, ctx: AppContext):
        self._ctx = ctx

    async def transcribe(self, source: str, *, start=None, end=None, language: str | None = None,
                         timestamps: bool = False, model: str | None = None) -> str:
        resolved = self._ctx.models.resolve("transcribe", model)
        if resolved.supports(TRANSCRIPTION) is False:
            raise UnsupportedCapabilityError(
                f"{resolved.model} does not transcribe speech. Set `transcribe_model` to a "
                "transcription model (for example openai/whisper-1).")
        kw: dict = {}
        if language:
            kw["language"] = language
        if timestamps:
            kw.update(_timing_params(resolved.vendor))
        limits = limits_for(resolved.vendor)
        async with prepare(self._ctx, source, start, end) as audio:
            seconds = limits.transcribe_seconds
            if timestamps and limits.timed_transcribe_seconds is not None:
                seconds = limits.timed_transcribe_seconds
            chunks = await self._chunks(audio, limits.transcribe_bytes, seconds)
            try:
                parts = await self._run(resolved, chunks, audio, kw, timestamps)
            finally:
                for chunk in chunks:
                    if chunk.path != audio.path:
                        with contextlib.suppress(OSError):
                            chunk.path.unlink()
        if timestamps:
            return mark_segments(parts, audio.offset)
        return "\n".join(text for _, text in parts)

    async def _chunks(self, audio: PreparedAudio, max_bytes: int | None,
                      max_seconds: float | None) -> list[_Chunk]:
        """The whole audio when it fits one request, else chunks cut at silence.

        A request is limited by file size, by duration, or both; a chunk must respect the
        tighter one. A limit that is not known cuts nothing.
        """
        whole = [_Chunk(audio.path, 0.0, audio.duration)]
        over_size = max_bytes is not None and audio.size > max_bytes
        over_duration = max_seconds is not None and audio.duration > max_seconds * SIZE_MARGIN
        if not (over_size or over_duration):
            return whole
        ffmpeg = self._ctx.ffmpeg
        allowed = []
        if max_bytes is not None:
            allowed.append(max_bytes * SIZE_MARGIN / BYTES_PER_SECOND)
        if max_seconds is not None:
            allowed.append(max_seconds * SIZE_MARGIN)
        longest = min(allowed)
        silences = await ffmpeg.detect_silences(audio.path)
        chunks = plan_chunks(audio.duration, silences, longest * TARGET_SHARE, longest)
        if len(chunks) < 2:
            return whole
        files = await ffmpeg.split_at(audio.path, [start for start, _ in chunks[1:]])
        if len(files) != len(chunks):
            for file in files:
                with contextlib.suppress(OSError):
                    file.unlink()
            raise FFmpegError(
                f"Cutting the recording gave {len(files)} chunks, expected {len(chunks)}.")
        return [_Chunk(file, start, end)
                for file, (start, end) in zip(files, chunks, strict=True)]

    async def _send(self, resolved, chunk: _Chunk, kw: dict):
        """One request; a rate limit is waited out and the same chunk sent again."""
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            try:
                with chunk.path.open("rb") as handle:
                    return await self._ctx.llm.transcribe(resolved, handle, **kw)
            except RateLimitError as exc:
                if attempt == RATE_LIMIT_RETRIES:
                    raise
                wait = min(exc.retry_after or DEFAULT_WAIT, MAX_WAIT) + 1
                log.warning("Rate limited; sending the same chunk again in %.0f s (%d of %d)",
                            wait, attempt + 1, RATE_LIMIT_RETRIES)
                await _pause(wait)

    async def _run(self, resolved, chunks: list[_Chunk], audio: PreparedAudio, kw: dict,
                   timestamps: bool) -> list[Segment]:
        """The transcript of every chunk, in order; a segment starts in the prepared audio."""
        parts: list[Segment] = []
        failures: list[ModelError] = []
        answered = 0
        for index, chunk in enumerate(chunks):
            try:
                response = await self._send(resolved, chunk, kw)
            except ProviderError as exc:
                if len(chunks) == 1:
                    raise
                failures.append(exc)
                parts.append(_hole(chunk, audio.offset, exc))
                continue
            except RateLimitError as exc:
                # The provider keeps refusing: what is done is kept, the rest is marked, and
                # nothing more is sent.
                if len(chunks) == 1 or not answered:
                    raise
                failures.append(exc)
                parts.append(_hole(chunk, audio.offset, exc))
                parts.extend(_hole(rest, audio.offset, "not sent after the rate limit above")
                             for rest in chunks[index + 1:])
                break
            answered += 1
            parts.extend(_segments_of(response, chunk.start, timestamps, resolved.model))
        if not answered and len(chunks) > 1:
            raise failures[0]           # nothing was transcribed at all
        return parts


def _hole(chunk: _Chunk, offset: float, reason) -> Segment:
    """Never drop a chunk silently: the hole is marked where it is in the transcript."""
    first, last = (format_time(offset + t) for t in (chunk.start, chunk.end))
    return Segment(chunk.start, f"[not transcribed {first}-{last}: {reason}]")


def _segments_of(response, chunk_start: float, timestamps: bool, model: str) -> list[Segment]:
    """What one answer says, with its times moved to where the chunk starts."""
    if not timestamps:
        text = _text(response)
        return [Segment(chunk_start, text)] if text else []
    lines = _segments(response) or group_words(_words(response))
    if not lines and _text(response):
        raise UnsupportedCapabilityError(
            f"{model} returns no timestamps. Call again without `timestamps`, "
            "or set `transcribe_model` to a model that returns them (for example "
            "openai/whisper-1).")
    return [Segment(chunk_start + line.start, line.text) for line in lines]


def _timing_params(vendor: str) -> dict:
    """How each vendor is asked for times (LiteLLM passes these through).

    Gemini's transcription models time every word and ignore ``verbose_json``; the others
    answer ``verbose_json`` with timed segments if they can time anything.
    """
    if vendor == "gemini":
        return {"timestamp_granularities": ["word"]}
    return {"response_format": "verbose_json"}


def _text(response) -> str:
    return (field(response, "text") or "").strip()


def _segments(response) -> list[Segment]:
    found = []
    for segment in field(response, "segments") or []:
        start, text = field(segment, "start"), (field(segment, "text") or "").strip()
        if start is not None and text:
            found.append(Segment(float(start), text))
    return found


def _words(response) -> list[Word]:
    found = []
    for word in field(response, "words") or []:
        start, end = field(word, "start"), field(word, "end")
        text = field(word, "word") or field(word, "text") or ""
        if start is not None and text.strip():
            found.append(Word(float(start), None if end is None else float(end), text))
    return found

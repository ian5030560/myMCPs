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

from .limits import limits_for
from .planner import plan_chunks
from .prepare import BYTES_PER_SECOND, PreparedAudio, prepare
from .timestamps import Word, format_time, group_words, mark_segments

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
    await asyncio.sleep(seconds)


@dataclass
class _Piece:
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
            pieces = await self._pieces(audio, limits.transcribe_bytes, seconds)
            try:
                parts = await self._run(resolved, pieces, audio, kw, timestamps)
            finally:
                for piece in pieces:
                    if piece.path != audio.path:
                        with contextlib.suppress(OSError):
                            piece.path.unlink()
        if timestamps:
            return mark_segments(parts, audio.offset)
        return "\n".join(text for _, text in parts)

    async def _pieces(self, audio: PreparedAudio, max_bytes: int | None,
                      max_seconds: float | None) -> list[_Piece]:
        """The whole audio when it fits one request, else chunks cut at silence.

        A request is limited by file size, by duration, or both; a chunk must respect the
        tighter one. A limit that is not known cuts nothing.
        """
        whole = [_Piece(audio.path, 0.0, audio.duration)]
        too_big = max_bytes is not None and audio.size > max_bytes
        too_long = max_seconds is not None and audio.duration > max_seconds * SIZE_MARGIN
        if not (too_big or too_long):
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
                f"Cutting the recording gave {len(files)} pieces, expected {len(chunks)}.")
        return [_Piece(file, start, end)
                for file, (start, end) in zip(files, chunks, strict=True)]

    async def _send(self, resolved, piece: _Piece, kw: dict):
        """One request; a rate limit is waited out and the same piece sent again."""
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            try:
                with piece.path.open("rb") as handle:
                    return await self._ctx.llm.transcribe(resolved, handle, **kw)
            except RateLimitError as exc:
                if attempt == RATE_LIMIT_RETRIES:
                    raise
                wait = min(exc.retry_after or DEFAULT_WAIT, MAX_WAIT) + 1
                log.warning("Rate limited; sending the same chunk again in %.0f s (%d of %d)",
                            wait, attempt + 1, RATE_LIMIT_RETRIES)
                await _pause(wait)

    async def _run(self, resolved, pieces: list[_Piece], audio: PreparedAudio, kw: dict,
                   timestamps: bool) -> list[tuple[float, str]]:
        """``(start in the prepared audio, text)`` for every piece, in order."""
        parts: list[tuple[float, str]] = []
        answered = 0

        def hole(piece: _Piece, reason) -> tuple[float, str]:
            # Never drop a chunk silently: the hole is marked where it is in the transcript.
            first, last = (format_time(audio.offset + t) for t in (piece.start, piece.end))
            return piece.start, f"[not transcribed {first}-{last}: {reason}]"

        failures: list[ModelError] = []
        for index, piece in enumerate(pieces):
            try:
                response = await self._send(resolved, piece, kw)
            except ProviderError as exc:
                if len(pieces) == 1:
                    raise
                failures.append(exc)
                parts.append(hole(piece, exc))
                continue
            except RateLimitError as exc:
                # The provider keeps refusing: what is done is kept, the rest is marked, and
                # nothing more is sent.
                if len(pieces) == 1 or not answered:
                    raise
                failures.append(exc)
                parts.append(hole(piece, exc))
                parts.extend(hole(rest, "not sent after the rate limit above")
                             for rest in pieces[index + 1:])
                break
            answered += 1
            if not timestamps:
                if text := _text(response):
                    parts.append((piece.start, text))
                continue
            lines = _segments(response) or group_words(_words(response))
            if not lines and _text(response):
                raise UnsupportedCapabilityError(
                    f"{resolved.model} returns no timestamps. Call again without `timestamps`, "
                    "or set `transcribe_model` to a model that returns them (for example "
                    "openai/whisper-1).")
            parts.extend((piece.start + start, text) for start, text in lines)
        if not answered and len(pieces) > 1:
            raise failures[0]           # nothing was transcribed at all
        return parts


def _timing_params(vendor: str) -> dict:
    """How each vendor is asked for times (LiteLLM passes these through).

    Gemini's transcription models time every word and ignore ``verbose_json``; the others
    answer ``verbose_json`` with timed segments if they can time anything.
    """
    if vendor == "gemini":
        return {"timestamp_granularities": ["word"]}
    return {"response_format": "verbose_json"}


def _field(obj, name):
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def _text(response) -> str:
    return (_field(response, "text") or "").strip()


def _segments(response) -> list[tuple[float, str]]:
    found = []
    for segment in _field(response, "segments") or []:
        start, text = _field(segment, "start"), (_field(segment, "text") or "").strip()
        if start is not None and text:
            found.append((float(start), text))
    return found


def _words(response) -> list[Word]:
    found = []
    for word in _field(response, "words") or []:
        start, end = _field(word, "start"), _field(word, "end")
        text = _field(word, "word") or _field(word, "text") or ""
        if start is not None and text.strip():
            found.append(Word(float(start), None if end is None else float(end), text))
    return found

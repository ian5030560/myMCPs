"""Speech to text.

A recording that fits one request is sent whole. A longer one is cut into chunks at silence,
each chunk is transcribed, and the times are moved back onto the original recording (ADR 0005).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from pathlib import Path

from mymcps.core.abilities import TRANSCRIPTION
from mymcps.core.context import AppContext
from mymcps.core.errors import FFmpegError, ProviderError, UnsupportedCapabilityError

from .limits import limits_for
from .planner import plan_chunks
from .prepare import BYTES_PER_SECOND, PreparedAudio, prepare
from .timestamps import Word, format_time, group_words, mark_segments

# A chunk is planned to fill this much of what one request carries, leaving room for headers.
SIZE_MARGIN = 0.95
# Where a cut is aimed at, as a share of the longest allowed chunk.
TARGET_SHARE = 0.9


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
        limit = limits_for(resolved.vendor).transcribe_bytes
        async with prepare(self._ctx, source, start, end) as audio:
            pieces = await self._pieces(audio, limit)
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

    async def _pieces(self, audio: PreparedAudio, limit: int | None) -> list[_Piece]:
        """The whole audio when it fits one request, else chunks cut at silence."""
        whole = [_Piece(audio.path, 0.0, audio.duration)]
        if limit is None or audio.size <= limit:
            return whole
        ffmpeg = self._ctx.ffmpeg
        longest = limit * SIZE_MARGIN / BYTES_PER_SECOND
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

    async def _run(self, resolved, pieces: list[_Piece], audio: PreparedAudio, kw: dict,
                   timestamps: bool) -> list[tuple[float, str]]:
        """``(start in the prepared audio, text)`` for every piece, in order."""
        parts: list[tuple[float, str]] = []
        failures: list[ProviderError] = []
        for piece in pieces:
            try:
                with piece.path.open("rb") as handle:
                    response = await self._ctx.llm.transcribe(resolved, handle, **kw)
            except ProviderError as exc:
                if len(pieces) == 1:
                    raise
                # Never drop a chunk silently: the hole is marked where it is in the transcript.
                failures.append(exc)
                first, last = (format_time(audio.offset + t) for t in (piece.start, piece.end))
                parts.append((piece.start, f"[not transcribed {first}-{last}: {exc}]"))
                continue
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
        if len(failures) == len(pieces) > 1:
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

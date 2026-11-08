"""What a model call gives back, as plain values.

LiteLLM answers with objects or with dicts, depending on the vendor and the version. The
conversion happens once, in :class:`~mymcps.core.llm.LLMClient`, so nothing else has to know
what a LiteLLM response looks like.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as _dc_field
from typing import Any, NamedTuple


class Segment(NamedTuple):
    """A short timed piece of transcript, as a model returns it or as words are grouped."""

    start: float        # seconds
    text: str


@dataclass(frozen=True)
class Word:
    start: float
    end: float | None
    text: str


@dataclass(frozen=True)
class Transcription:
    text: str                                                   # stripped; may be empty
    segments: list[Segment] = _dc_field(default_factory=list)   # timed sentences, if given
    words: list[Word] = _dc_field(default_factory=list)         # timed words, if given


@dataclass(frozen=True)
class GeneratedImage:
    b64: str | None = None
    url: str | None = None


def _get(obj: Any, name: str) -> Any:
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def transcription_from(response: Any) -> Transcription:
    segments = []
    for item in _get(response, "segments") or []:
        start, text = _get(item, "start"), (_get(item, "text") or "").strip()
        if start is not None and text:
            segments.append(Segment(float(start), text))
    words = []
    for item in _get(response, "words") or []:
        start, end = _get(item, "start"), _get(item, "end")
        text = _get(item, "word") or _get(item, "text") or ""
        if start is not None and text.strip():
            words.append(Word(float(start), None if end is None else float(end), text))
    return Transcription((_get(response, "text") or "").strip(), segments, words)


def images_from(response: Any) -> list[GeneratedImage]:
    return [GeneratedImage(_get(item, "b64_json") or None, _get(item, "url") or None)
            for item in _get(response, "data") or []]


def completion_text(response: Any) -> str | None:
    """The first choice's text (stripped), or None when the response has no choice."""
    try:
        content = _get(_get(_get(response, "choices")[0], "message"), "content")
    except (IndexError, TypeError):
        return None
    return (content or "").strip()


def file_id_from(response: Any) -> str | None:
    return _get(response, "id") or None

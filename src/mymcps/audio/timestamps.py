"""The ``[hh:mm:ss]`` time marks both audio tools put in their output.

Times always count from the start of the original recording, also when ``start`` was given.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import NamedTuple

# [mm:ss] or [hh:mm:ss], as a model writes it when asked to cite moments.
_CITED = re.compile(r"\[(\d{1,3}):(\d{2})(?::(\d{2}))?\]")


def format_time(seconds: float) -> str:
    total = int(max(seconds, 0) + 0.5)          # rounded, half up (not Python's round-to-even)
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


class Segment(NamedTuple):
    """A short timed piece of transcript, as a model returns it or as words are grouped."""

    start: float        # seconds
    text: str


@dataclass(frozen=True)
class Word:
    start: float
    end: float | None
    text: str


# Some models time every word instead of every sentence. Words are grouped into lines of
# about a sentence each, by the only two things that never depend on the language or on
# punctuation: a pause, and a limit on how much one time mark may cover.
PAUSE_SECONDS = 0.8        # a longer silence between two words starts a new line
MAX_LINE_SECONDS = 10.0    # a line never starts more than this long after its first word


def group_words(words: Iterable[Word], pause: float = PAUSE_SECONDS,
                max_seconds: float = MAX_LINE_SECONDS) -> list[Segment]:
    """Group timed words into ``Segment`` lines, in the order given.

    A line ends at a pause longer than ``pause`` (measured from one word's end to the next
    word's start; skipped when the end is unknown) or when the next word would start
    ``max_seconds`` or more after the line's first word.
    """
    lines: list[tuple[float, list[str]]] = []
    previous: Word | None = None
    for word in words:
        if not word.text.strip():
            continue
        new_line = previous is None or (
            (previous.end is not None and word.start - previous.end > pause)
            or word.start - lines[-1][0] >= max_seconds)
        if new_line:
            lines.append((word.start, [word.text.strip()]))
        else:
            lines[-1][1].append(word.text.strip())
        previous = word
    return [Segment(start, _join(parts)) for start, parts in lines]


def _join(parts: list[str]) -> str:
    """Words joined with spaces, except between two CJK characters (they have none)."""
    text = parts[0]
    for part in parts[1:]:
        text += ("" if _is_cjk(text[-1]) and _is_cjk(part[0]) else " ") + part
    return text


def _is_cjk(char: str) -> bool:
    return any(low <= ord(char) <= high for low, high in _CJK)


_CJK = ((0x2E80, 0x9FFF), (0xAC00, 0xD7AF), (0xF900, 0xFAFF), (0xFF00, 0xFFEF))


def mark_segments(segments: Iterable[Segment], offset: float) -> str:
    """One line per segment, each led by its start time."""
    return "\n".join(f"[{format_time(offset + start)}] {text}" for start, text in segments)


def shift_cited_times(text: str, offset: float) -> tuple[str, int]:
    """Rewrite every cited time in ``text`` onto the original recording.

    A model hears only the part that was sent, so the times it cites count from that part's
    start. Returns the new text and how many times were found.
    """
    def shifted(match: re.Match) -> str:
        first, second, third = match.groups()
        if third is None:
            seconds = int(first) * 60 + int(second)
        else:
            seconds = int(first) * 3600 + int(second) * 60 + int(third)
        return f"[{format_time(offset + seconds)}]"

    return _CITED.subn(shifted, text)

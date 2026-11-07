"""Where to cut a long recording into chunks (pure planning, no ffmpeg, no I/O).

The caller detects the silences; this module only decides the cuts. A cut falls inside the
silence nearest the target chunk length, so words are not cut in half; when no silence is in
reach, it falls on the target length itself (ADR 0005).
"""

from __future__ import annotations

Span = tuple[float, float]


def plan_chunks(duration: float, silences: list[Span], target: float,
                maximum: float) -> list[Span]:
    """Split ``[0, duration]`` into consecutive chunks of at most ``maximum`` seconds.

    ``silences`` are ``(start, end)`` spans in seconds, in any order; spans outside the
    recording are clipped and empty ones ignored. Chunks are contiguous, so they cover the whole
    recording with no gap and no overlap, and none is empty. A recording that already fits in
    ``maximum`` is one chunk. Each cut is made after at least ``target / 2`` seconds of the
    chunk, as close to ``target`` as the silences allow, and never later than ``maximum``.
    """
    if not 0 < target <= maximum:
        raise ValueError("target must be positive and not larger than maximum")
    if duration <= 0:
        return []
    spans = _clean(silences, duration)
    chunks: list[Span] = []
    pos = 0.0
    while duration - pos > maximum:
        cut = _next_cut(pos, spans, target, maximum)
        chunks.append((pos, cut))
        pos = cut
    chunks.append((pos, duration))
    return chunks


def _clean(silences: list[Span], duration: float) -> list[Span]:
    clipped = [(max(s, 0.0), min(e, duration)) for s, e in silences]
    return sorted(span for span in clipped if span[0] < span[1])


def _next_cut(pos: float, silences: list[Span], target: float, maximum: float) -> float:
    ideal = pos + target
    earliest, latest = pos + target / 2, pos + maximum
    best: float | None = None
    for start, end in silences:
        lo, hi = max(start, earliest), min(end, latest)
        if lo > hi:
            continue                        # this silence is out of reach
        cut = min(max(ideal, lo), hi)       # the point of the silence nearest the target
        if best is None or abs(cut - ideal) < abs(best - ideal):
            best = cut
    return ideal if best is None else best

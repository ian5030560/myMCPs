"""Where to cut a long recording into chunks (pure planning, no ffmpeg, no I/O).

The caller detects the silences; this module only decides the cuts. A cut falls inside a
silence so words are not cut in half, and well inside it: the edge of a detected silence is
where the level crosses the threshold, which is the soft end of a word, so a cut made there
loses it. Near the target length the longest silence is preferred, since a longer pause is more
likely a real break than a breath inside a phrase. When no silence is in reach, the cut falls on
the target length itself (ADR 0005).
"""

from __future__ import annotations

Span = tuple[float, float]

# A cut keeps this far from both ends of its silence (less when the silence is shorter: then it
# is cut in the middle).
MARGIN = 0.25
# Silences within this share of the target length (at most SEARCH_MAX seconds) either side of
# the ideal cut compete on length; the longest wins.
SEARCH_SHARE = 0.1
SEARCH_MAX = 60.0


def plan_chunks(duration: float, silences: list[Span], target: float,
                maximum: float) -> list[Span]:
    """Split ``[0, duration]`` into consecutive chunks of at most ``maximum`` seconds.

    ``silences`` are ``(start, end)`` spans in seconds, in any order; spans outside the
    recording are clipped and empty ones ignored. Chunks are contiguous, so they cover the whole
    recording with no gap and no overlap, and none is empty. A recording that already fits in
    ``maximum`` is one chunk. Each cut is made after at least ``target / 2`` seconds of the
    chunk, never later than ``maximum``, and in the middle of the longest silence near
    ``target`` (see :func:`_next_cut`).
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
    """Where the chunk starting at ``pos`` ends.

    Each silence offers the point nearest the target that is at least ``MARGIN`` (or half the
    silence) inside both of its ends and within reach. Of the offers within the search distance
    of the target the longest silence wins (nearest on a tie); if there are none, the nearest
    offer wins. A silence that overlaps the reach only at its very edge still offers that edge,
    so a cut is inside a silence whenever one is in reach at all.
    """
    ideal = pos + target
    earliest, latest = pos + target / 2, pos + maximum
    search = min(SEARCH_MAX, SEARCH_SHARE * target)
    offers: list[tuple[float, float]] = []          # (silence length, cut)
    edges: list[float] = []                          # fallback: any point of a silence in reach
    for start, end in silences:
        margin = min(MARGIN, (end - start) / 2)
        lo, hi = max(start + margin, earliest), min(end - margin, latest)
        if lo <= hi:
            offers.append((end - start, min(max(ideal, lo), hi)))
            continue
        lo, hi = max(start, earliest), min(end, latest)
        if lo <= hi:
            edges.append(min(max(ideal, lo), hi))
    near = [offer for offer in offers if abs(offer[1] - ideal) <= search]
    if near:
        return max(near, key=lambda offer: (offer[0], -abs(offer[1] - ideal)))[1]
    candidates = [cut for _, cut in offers] or edges
    return min(candidates, key=lambda cut: abs(cut - ideal)) if candidates else ideal

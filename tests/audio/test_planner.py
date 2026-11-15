import random

import pytest

from mymcps.audio.planner import MARGIN, plan_chunks

EPS = 1e-9


def check_properties(chunks, duration, silences, target, maximum):
    """What must hold whatever strategy picks the cuts."""
    assert chunks[0][0] == 0 and chunks[-1][1] == duration       # covers the whole recording
    for (_, end), (start, _) in zip(chunks, chunks[1:], strict=False):
        assert end == start                                      # no gap, no overlap
    for start, end in chunks:
        assert 0 < end - start <= maximum + EPS                  # never empty, never too long
    pos = 0.0
    for _, cut in chunks[:-1]:
        window = (pos + target / 2, pos + maximum)
        reachable = [s for s in silences
                     if max(s[0], window[0]) <= min(s[1], window[1])]
        if reachable:
            assert any(s[0] - EPS <= cut <= s[1] + EPS for s in reachable)   # inside a silence
        else:
            assert cut == pytest.approx(pos + target)                         # hard cut
        pos = cut


CASES = {
    "no silence at all": (100, [], 30, 40),
    "silence at the very start": (100, [(0, 5)], 30, 40),
    "silence at the very end": (100, [(95, 100)], 30, 40),
    "silence longer than a chunk": (200, [(10, 190)], 30, 40),
    "silence only past the maximum": (100, [(80, 90)], 30, 40),
    "silence only before half the target": (100, [(3, 5)], 30, 40),
    "dense silences": (100, [(i, i + 0.4) for i in range(0, 100)], 30, 40),
    "unsorted and overlapping silences": (100, [(50, 55), (20, 35), (30, 40)], 30, 40),
    "silence outside the recording": (100, [(-10, -1), (120, 130), (-5, 2)], 30, 40),
    "empty silence spans": (100, [(10, 10), (20, 19)], 30, 40),
    "target equals maximum": (100, [(25, 26), (70, 71)], 30, 30),
}


@pytest.mark.parametrize("duration,silences,target,maximum", CASES.values(), ids=CASES.keys())
def test_properties_on_edge_cases(duration, silences, target, maximum):
    chunks = plan_chunks(duration, silences, target, maximum)
    check_properties(chunks, duration, [s for s in silences if s[0] < s[1]], target, maximum)


@pytest.mark.parametrize("seed", range(200))
def test_properties_on_random_recordings(seed):
    rng = random.Random(seed)
    duration = rng.uniform(1, 2000)
    maximum = rng.uniform(5, 400)
    target = rng.uniform(maximum / 4, maximum)
    silences = []
    for _ in range(rng.randint(0, 60)):
        start = rng.uniform(-20, duration + 20)
        silences.append((start, start + rng.uniform(0, rng.choice([1, 5, 300]))))
    chunks = plan_chunks(duration, silences, target, maximum)
    clean = [(max(s, 0), min(e, duration)) for s, e in silences if max(s, 0) < min(e, duration)]
    check_properties(chunks, duration, clean, target, maximum)


@pytest.mark.parametrize("duration,expected_chunks", [
    (39.999, 1), (40, 1), (40.001, 2), (0.5, 1)])
def test_a_recording_that_fits_is_one_chunk(duration, expected_chunks):
    chunks = plan_chunks(duration, [], 30, 40)
    assert len(chunks) == expected_chunks
    check_properties(chunks, duration, [], 30, 40)


def test_empty_recording_has_no_chunks():
    assert plan_chunks(0, [(0, 1)], 30, 40) == []


def test_cuts_in_the_silence_nearest_the_target():
    # target 30, window 15..40, search distance 3: no silence is that close, so the nearest offer
    # wins: 18-19 offers 18.75, 33-34 offers 33.25, 39-40 offers 39.25
    chunks = plan_chunks(100, [(18, 19), (39, 40), (33, 34)], 30, 40)
    assert chunks[0] == (0, pytest.approx(33.25))


def test_cuts_in_the_middle_of_a_short_silence_not_at_its_edge():
    # the silence 33-33.4 does not contain the target; its edge (33) would be the nearest point
    assert plan_chunks(100, [(33, 33.4)], 30, 40)[0] == (0, pytest.approx(33.2))


def test_cuts_clear_of_the_edges_of_a_long_silence():
    # the silence 28-45 contains the target, so the cut is the target
    assert plan_chunks(100, [(28, 45)], 30, 40)[0] == (0, 30)
    # the silence 10-25 ends before the target: the cut keeps MARGIN away from its end
    assert plan_chunks(100, [(10, 25)], 30, 40)[0] == (0, pytest.approx(25 - MARGIN))
    # and a silence that starts after the target keeps the margin from its start
    assert plan_chunks(100, [(32, 38)], 30, 40)[0] == (0, pytest.approx(32 + MARGIN))


def test_prefers_the_longest_silence_near_the_target():
    # search distance is 3 s: 29-29.4 (0.6 away, short) loses to 31-32.5 (1.5 away, longer)
    chunks = plan_chunks(100, [(29, 29.4), (31, 32.5)], 30, 40)
    assert chunks[0] == (0, pytest.approx(31 + MARGIN))


def test_a_longer_silence_beyond_the_search_distance_does_not_win():
    # 29-29.4 is near; the long silence at 36-40 is 6 s away, past the 3 s search distance
    assert plan_chunks(100, [(29, 29.4), (36, 40)], 30, 40)[0] == (0, pytest.approx(29.2))


def test_a_silence_barely_in_reach_still_gets_the_cut():
    # window is 15..40; the silence ends at 15.1, and the part in reach is too small to keep a
    # margin, so the cut is its end
    assert plan_chunks(100, [(14, 15.1)], 30, 40)[0] == (0, pytest.approx(15.1))


def test_without_a_silence_in_reach_the_cut_is_at_the_target():
    assert plan_chunks(100, [(80, 90)], 30, 40)[0] == (0, 30)


@pytest.mark.parametrize("target,maximum", [(0, 10), (-1, 10), (11, 10)])
def test_rejects_impossible_settings(target, maximum):
    with pytest.raises(ValueError):
        plan_chunks(100, [], target, maximum)

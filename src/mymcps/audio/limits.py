"""What each vendor accepts in one request. The one place to edit when a vendor changes.

Sizes are decimal megabytes (the smaller reading of "MB"), so a file near the limit is not sent
on a technicality. A vendor that is not listed, or a limit that is not set, is unknown: nothing
is split or refused for it and the vendor's own error is passed on.
"""

from __future__ import annotations

from dataclasses import dataclass

MB = 1_000_000
HOUR = 3600.0


@dataclass(frozen=True)
class VendorLimits:
    transcribe_bytes: int | None = None   # largest file one transcription request carries
    transcribe_seconds: float | None = None  # longest audio one transcription request carries
    timed_transcribe_seconds: float | None = None  # the same, when word times are asked for
    inline_bytes: int | None = None       # largest audio sent inside a chat request
    max_seconds: float | None = None      # longest recording one chat prompt takes
    files_api: bool = False               # bigger audio can be uploaded and referenced instead


# Gemini's transcription model takes "up to 1 hour per request (up to 30 minutes when speaker
# diarization or word-level timestamps are enabled)" (the model's documentation page). The 20 MB
# size limit alone would allow 83 minutes, which the model refuses: a 71 minute chunk failed on
# "more than 98304 input tokens" (audio is 25 tokens per second), and 48 minutes with word times
# came back with status "incomplete".
LIMITS: dict[str, VendorLimits] = {
    "gemini": VendorLimits(transcribe_bytes=20 * MB, transcribe_seconds=1 * HOUR,
                           timed_transcribe_seconds=0.5 * HOUR, inline_bytes=20 * MB,
                           max_seconds=9.5 * HOUR, files_api=True),
    "openai": VendorLimits(transcribe_bytes=25 * MB),
}


def limits_for(vendor: str) -> VendorLimits:
    return LIMITS.get(vendor, VendorLimits())

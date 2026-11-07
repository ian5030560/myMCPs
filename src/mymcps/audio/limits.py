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
    inline_bytes: int | None = None       # largest audio sent inside a chat request
    max_seconds: float | None = None      # longest recording one chat prompt takes
    files_api: bool = False               # bigger audio can be uploaded and referenced instead


LIMITS: dict[str, VendorLimits] = {
    "gemini": VendorLimits(transcribe_bytes=20 * MB, inline_bytes=20 * MB,
                           max_seconds=9.5 * HOUR, files_api=True),
    "openai": VendorLimits(transcribe_bytes=25 * MB),
}


def limits_for(vendor: str) -> VendorLimits:
    return LIMITS.get(vendor, VendorLimits())

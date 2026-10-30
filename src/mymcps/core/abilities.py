"""What a model can do, derived rather than declared.

The source is LiteLLM's model table (read through :class:`~mymcps.core.llm.LLMClient`) plus one
vendor rule: Gemini chat models read video directly. A model that is absent from the table is
*unknown* (``None``) on every count, never "incapable": LiteLLM's own helpers answer "no" for
models it has never heard of, which would reject every self-hosted or brand-new model.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

# Ability names, as shown by list_models.
CHAT = "chat"
IMAGE_OUTPUT = "image_output"
TRANSCRIPTION = "transcription"
VISION = "vision"
AUDIO_INPUT = "audio_input"
VIDEO_INPUT = "video_input"

_IMAGE_MODES = ("image_generation", "image_edit")


@dataclass(frozen=True)
class TableEntry:
    """What LiteLLM's table says about one model."""

    mode: str | None = None
    vision: bool = False
    audio_input: bool = False


def derive(entry: TableEntry | None, vendor: str) -> frozenset[str] | None:
    """The abilities of a model, or None when the table does not know it."""
    if entry is None:
        return None
    found: set[str] = set()
    if entry.mode == "chat":
        found.add(CHAT)
        if vendor == "gemini":
            found.add(VIDEO_INPUT)
    elif entry.mode in _IMAGE_MODES:
        found.add(IMAGE_OUTPUT)
    elif entry.mode == "audio_transcription":
        found.add(TRANSCRIPTION)
    if entry.vision:
        found.add(VISION)
    if entry.audio_input:
        found.add(AUDIO_INPUT)
    return frozenset(found)


@dataclass(frozen=True)
class Need:
    """What a purpose requires of its model, checked at startup (warning only)."""

    description: str
    met: Callable[[frozenset[str]], bool]


# The needs the servers declare for their purposes.
PRODUCES_IMAGES = Need("a model that produces images", lambda a: IMAGE_OUTPUT in a)
WATCHES_VIDEO = Need(
    "a chat model that reads video or images",
    lambda a: CHAT in a and (VIDEO_INPUT in a or VISION in a))
HEARS_AUDIO = Need("a chat model that accepts audio", lambda a: CHAT in a and AUDIO_INPUT in a)
TRANSCRIBES = Need("a model that transcribes speech", lambda a: TRANSCRIPTION in a)

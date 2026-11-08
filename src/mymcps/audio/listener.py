"""Answering a question about a recording. The whole recording goes in one request (ADR 0005)."""

from __future__ import annotations

import base64
import contextlib
import logging
from collections.abc import AsyncIterator

from mymcps.core.abilities import AUDIO_INPUT, CHAT
from mymcps.core.context import AppContext
from mymcps.core.errors import (
    InputError,
    ModelError,
    ProviderError,
    UnsupportedCapabilityError,
)

from .limits import VendorLimits, limits_for
from .prepare import PreparedAudio, RecordingTooLong, prepare
from .timestamps import shift_cited_times

log = logging.getLogger(__name__)

_CITE = ("\n\nWhere it helps, cite moments in the audio as [hh:mm:ss], counted from the start "
         "of this audio.")
_MIME = "audio/mpeg"
_TOO_LONG = (
    "The recording is {hours:.1f} hours, over the {limit:.1f} hours {vendor} takes in one "
    "request. `listen_audio` never splits a recording, because only you know whether your "
    "question survives being split. Either (1) work through the recording in order with "
    "`start` and `end`, carrying your notes so far into the next `prompt`, or (2) call "
    "`transcribe_audio` first and work from the text.")


class Listener:
    def __init__(self, ctx: AppContext):
        self._ctx = ctx

    async def listen(self, source: str, prompt: str, *, start=None, end=None,
                     timestamps: bool = False, model: str | None = None) -> str:
        resolved = self._ctx.models.resolve("listen", model)
        if resolved.supports(CHAT) is False or resolved.supports(AUDIO_INPUT) is False:
            raise UnsupportedCapabilityError(
                f"{resolved.model} does not accept audio. Set `listen_model` to a chat model "
                "that hears audio (for example gemini/gemini-2.5-flash).")
        limits = limits_for(resolved.vendor)

        try:
            async with prepare(self._ctx, source, start, end,
                               max_seconds=limits.max_seconds) as audio:
                question = prompt + (_CITE if timestamps else "")
                async with self._audio_part(resolved, audio, limits) as part:
                    reply = await self._ctx.llm.complete(resolved, [{"role": "user", "content": [
                        {"type": "text", "text": question}, part]}])
        except RecordingTooLong as exc:
            raise InputError(_TOO_LONG.format(
                hours=exc.seconds / 3600, limit=exc.limit / 3600, vendor=resolved.vendor)) from exc
        answer = _answer(reply, resolved.model)
        if not timestamps:
            return answer
        answer, found = shift_cited_times(answer, audio.offset)
        if not found:
            raise UnsupportedCapabilityError(
                f"{resolved.model} gave no timestamps in its answer. Call again without "
                "`timestamps`, or ask for the moments in the `prompt`.")
        return answer

    @contextlib.asynccontextmanager
    async def _audio_part(self, resolved, audio: PreparedAudio,
                          limits: VendorLimits) -> AsyncIterator[dict]:
        """The message part that carries the audio: inline when small, else uploaded.

        An upload is always deleted on exit, also after an error.
        """
        if limits.inline_bytes is None or audio.size <= limits.inline_bytes:
            data = base64.b64encode(audio.path.read_bytes()).decode()
            yield {"type": "input_audio", "input_audio": {"data": data, "format": "mp3"}}
            return
        if not limits.files_api:
            raise InputError(
                f"The compressed audio is {audio.size / 1e6:.1f} MB, over the "
                f"{limits.inline_bytes / 1e6:.0f} MB {resolved.vendor} takes in one "
                "request. Use a shorter range with `start` and `end`.")
        file_id = await self._upload(resolved, audio)
        try:
            yield {"type": "file", "file": {"file_id": file_id, "format": _MIME}}
        finally:
            await self._delete(resolved, file_id)

    async def _upload(self, resolved, audio: PreparedAudio) -> str:
        with audio.path.open("rb") as handle:
            return await self._ctx.llm.upload_file(resolved, handle)

    async def _delete(self, resolved, file_id: str) -> None:
        """Leave nothing behind at the vendor. A failure here must not lose the answer."""
        try:
            await self._ctx.llm.delete_file(resolved, file_id)
        except ModelError as exc:
            log.warning("could not delete the uploaded audio %s: %s", file_id, exc)


def _answer(text: str, model: str) -> str:
    if not text:
        raise ProviderError(f"{model} returned an empty answer.")
    return text

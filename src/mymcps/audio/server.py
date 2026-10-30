from __future__ import annotations

from mymcps.core.abilities import HEARS_AUDIO, TRANSCRIBES
from mymcps.core.server import BaseMediaServer
from mymcps.core.spec import Purpose, ServerSpec


class AudioServer(BaseMediaServer):
    spec = ServerSpec("audio", purposes=(
        Purpose("listen", "answering questions about, summarising and translating audio",
                HEARS_AUDIO),
        Purpose("transcribe", "speech to text", TRANSCRIBES),
    ))
    instructions = "Understand audio: transcription, Q&A, summaries and translation."
    default_port = 8703

    def register_tools(self) -> None:
        pass  # transcription tools arrive in the next stage


main = AudioServer.main

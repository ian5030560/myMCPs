from __future__ import annotations

from mymcps.core.server import BaseMediaServer


class AudioListenServer(BaseMediaServer):
    name = "audio_listen"
    cli_name = "audio-listen"
    instructions = "Understand audio: transcription, Q&A, summaries and translation."
    default_port = 8703

    def register_tools(self) -> None:
        pass  # transcription tools arrive in the next stage


main = AudioListenServer.main

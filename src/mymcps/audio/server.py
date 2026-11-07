from __future__ import annotations

from mymcps.core.abilities import HEARS_AUDIO, TRANSCRIBES
from mymcps.core.server import BaseMediaServer
from mymcps.core.spec import Purpose, ServerSpec

from .listener import Listener
from .transcriber import Transcriber


class AudioServer(BaseMediaServer):
    spec = ServerSpec("audio", purposes=(
        Purpose("listen", "answering questions about, summarising and translating audio",
                HEARS_AUDIO),
        Purpose("transcribe", "speech to text", TRANSCRIBES),
    ))
    instructions = (
        "Understand audio. `path` is a local path or an http(s) URL. `start` and `end` take "
        "seconds, mm:ss or hh:mm:ss, and limit the work to part of the recording. `model` is "
        "an alias from list_models or a LiteLLM string such as openai/whisper-1.")
    default_port = 8703

    def register_tools(self) -> None:
        transcriber, listener = Transcriber(self.ctx), Listener(self.ctx)

        @self.mcp.tool()
        async def transcribe_audio(path: str, start: str | float | None = None,
                                   end: str | float | None = None, language: str | None = None,
                                   timestamps: bool = False, model: str | None = None) -> str:
            """Transcribe speech in an audio (or video) file to text.

            Args:
                path: Local path or http(s) URL of the recording.
                start: Where to begin (seconds, mm:ss or hh:mm:ss). Defaults to the beginning.
                end: Where to stop. Defaults to the end.
                language: Language spoken, as an ISO-639-1 code such as "en" or "zh" (helps
                    accuracy when you know it).
                timestamps: Put [hh:mm:ss] before each segment, counted from the start of the
                    original recording. Fails if the model returns no times.
                model: Model alias or LiteLLM string. Defaults to the configured
                    `transcribe_model`.
            """
            return await transcriber.transcribe(path, start=start, end=end, language=language,
                                                timestamps=timestamps, model=model)

        @self.mcp.tool()
        async def listen_audio(path: str, prompt: str, start: str | float | None = None,
                               end: str | float | None = None, timestamps: bool = False,
                               model: str | None = None) -> str:
            """Answer a question about an audio (or video) file by listening to it: who speaks,
            tone, music and other sounds, summaries, translation. The whole recording is sent in
            one request and never split, so the answer can span it.

            Args:
                path: Local path or http(s) URL of the recording.
                prompt: What you want to know.
                start: Where to begin (seconds, mm:ss or hh:mm:ss). Defaults to the beginning.
                end: Where to stop. Defaults to the end.
                timestamps: Ask the model to cite moments as [hh:mm:ss], counted from the start
                    of the original recording. Fails if the answer contains none.
                model: Model alias or LiteLLM string. Defaults to the configured `listen_model`.
            """
            return await listener.listen(path, prompt, start=start, end=end,
                                         timestamps=timestamps, model=model)


main = AudioServer.main

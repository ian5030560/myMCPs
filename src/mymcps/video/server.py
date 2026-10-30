from __future__ import annotations

from mymcps.core.abilities import WATCHES_VIDEO
from mymcps.core.server import BaseMediaServer
from mymcps.core.spec import Purpose, ServerSpec


class VideoServer(BaseMediaServer):
    spec = ServerSpec("video", purposes=(
        Purpose("watch", "summaries, Q&A and timestamped analysis of videos", WATCHES_VIDEO),
    ))
    instructions = "Watch videos: summaries, Q&A, timestamped analysis and frame extraction."
    default_port = 8702

    def register_tools(self) -> None:
        pass  # analysis tools arrive in the next stage


main = VideoServer.main

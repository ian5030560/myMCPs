from __future__ import annotations

from mymcps.core.server import BaseMediaServer


class VideoWatchServer(BaseMediaServer):
    name = "video_watch"
    cli_name = "video-watch"
    instructions = "Watch videos: summaries, Q&A, timestamped analysis and frame extraction."
    default_port = 8702

    def register_tools(self) -> None:
        pass  # analysis tools arrive in the next stage


main = VideoWatchServer.main

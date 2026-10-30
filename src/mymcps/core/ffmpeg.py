"""ffmpeg helpers shared by the video and audio servers (bundled imageio-ffmpeg binary)."""

from __future__ import annotations

import re
import secrets
import tempfile
from dataclasses import dataclass
from pathlib import Path

import anyio

from .errors import FFmpegError, MissingExtraError


@dataclass
class MediaInfo:
    duration: float
    has_video: bool
    has_audio: bool
    width: int | None = None
    height: int | None = None


class FFmpeg:
    def __init__(self, exe: str | Path, workdir: Path | None = None):
        self._exe = str(exe)
        self._workdir = workdir or Path(tempfile.gettempdir()) / "mymcps" / "work"

    @classmethod
    def bundled(cls, workdir: Path | None = None) -> FFmpeg:
        try:
            import imageio_ffmpeg
        except ImportError as exc:
            raise MissingExtraError("video", "imageio-ffmpeg") from exc
        return cls(imageio_ffmpeg.get_ffmpeg_exe(), workdir)

    # ── helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def parse_timestamp(value: float | int | str) -> float:
        """Seconds as a number, or ``[HH:]MM:SS[.ms]`` string -> seconds."""
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        try:
            return float(text)
        except ValueError:
            pass
        parts = text.split(":")
        if not 2 <= len(parts) <= 3:
            raise FFmpegError(f"Invalid timestamp: {value!r}")
        try:
            nums = [float(p) for p in parts]
        except ValueError as exc:
            raise FFmpegError(f"Invalid timestamp: {value!r}") from exc
        seconds = 0.0
        for n in nums:
            seconds = seconds * 60 + n
        return seconds

    def _new_path(self, stem: str, ext: str) -> Path:
        self._workdir.mkdir(parents=True, exist_ok=True)
        return self._workdir / f"{stem}-{secrets.token_hex(3)}.{ext}"

    async def _run(self, *args: str) -> str:
        cmd = [self._exe, "-hide_banner", "-loglevel", "error", "-y", *args]
        result = await anyio.run_process(cmd, check=False)
        if result.returncode != 0:
            tail = result.stderr.decode(errors="replace").strip()[-800:]
            raise FFmpegError(f"ffmpeg failed ({result.returncode}): {tail}")
        return result.stderr.decode(errors="replace")

    def _range(self, start, end) -> list[str]:
        args: list[str] = []
        if start is not None:
            args += ["-ss", str(self.parse_timestamp(start))]
        if end is not None:
            args += ["-to", str(self.parse_timestamp(end))]
        return args

    # ── operations ───────────────────────────────────────────────────────
    async def probe(self, path: Path) -> MediaInfo:
        # imageio-ffmpeg ships no ffprobe; `ffmpeg -i` prints the info and exits non-zero.
        result = await anyio.run_process([self._exe, "-hide_banner", "-i", str(path)], check=False)
        text = result.stderr.decode(errors="replace")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
        if not m:
            raise FFmpegError(f"Could not read media info: {text.strip()[-300:]}")
        duration = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
        video = re.search(r"Stream #.*Video:.*?(\d{2,5})x(\d{2,5})", text)
        return MediaInfo(
            duration=duration,
            has_video=bool(re.search(r"Stream #.*Video:", text)),
            has_audio=bool(re.search(r"Stream #.*Audio:", text)),
            width=int(video[1]) if video else None,
            height=int(video[2]) if video else None,
        )

    async def extract_frames(self, path: Path, *, times: list | None = None,
                             fps: float | None = None, start=None, end=None,
                             max_side: int = 768) -> list[Path]:
        scale = f"scale='min({max_side},iw)':-2"
        if times:
            out = []
            for t in times:
                dest = self._new_path("frame", "jpg")
                await self._run("-ss", str(self.parse_timestamp(t)), "-i", str(path),
                                "-frames:v", "1", "-vf", scale, "-q:v", "3", str(dest))
                out.append(dest)
            return out
        self._workdir.mkdir(parents=True, exist_ok=True)
        prefix = f"frames-{secrets.token_hex(3)}"
        pattern = self._workdir / f"{prefix}-%04d.jpg"
        vf = f"fps={fps or 1},{scale}"
        await self._run(*self._range(start, end), "-i", str(path), "-vf", vf,
                        "-q:v", "3", str(pattern))
        return sorted(self._workdir.glob(f"{prefix}-*.jpg"))

    async def extract_audio(self, path: Path, *, start=None, end=None, fmt: str = "mp3",
                            bitrate: str = "64k") -> Path:
        dest = self._new_path("audio", fmt)
        await self._run(*self._range(start, end), "-i", str(path), "-vn",
                        "-ac", "1", "-b:a", bitrate, str(dest))
        return dest

    async def cut(self, path: Path, start, end) -> Path:
        dest = self._new_path("cut", path.suffix.lstrip(".") or "mp4")
        await self._run(*self._range(start, end), "-i", str(path), str(dest))
        return dest

    async def split(self, path: Path, segment_seconds: float) -> list[Path]:
        ext = path.suffix.lstrip(".") or "mp3"
        self._workdir.mkdir(parents=True, exist_ok=True)
        prefix = f"seg-{secrets.token_hex(3)}"
        pattern = self._workdir / f"{prefix}-%03d.{ext}"
        await self._run("-i", str(path), "-f", "segment", "-segment_time", str(segment_seconds),
                        "-c", "copy", "-reset_timestamps", "1", str(pattern))
        return sorted(self._workdir.glob(f"{prefix}-*.{ext}"))

    async def compress(self, path: Path, *, max_height: int = 480,
                       fps: float | None = None) -> Path:
        dest = self._new_path("small", "mp4")
        vf = f"scale=-2:'min({max_height},ih)'" + (f",fps={fps}" if fps else "")
        await self._run("-i", str(path), "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "30", "-c:a", "aac", "-b:a", "64k", str(dest))
        return dest

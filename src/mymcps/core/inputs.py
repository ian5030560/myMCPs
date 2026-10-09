"""Resolve user-supplied sources (local path or http(s) URL) into local files."""

from __future__ import annotations

import base64
import contextlib
import mimetypes
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from .config import Settings
from .errors import AccessDeniedError, DownloadError, InputNotFoundError

for _ext, _mime in {
    ".m4a": "audio/mp4", ".mkv": "video/x-matroska", ".webm": "video/webm",
    ".flac": "audio/flac", ".opus": "audio/opus", ".webp": "image/webp",
}.items():
    mimetypes.add_type(_mime, _ext)


@dataclass
class MediaInput:
    path: Path
    mime: str
    size: int
    is_temp: bool = False

    async def __aenter__(self) -> MediaInput:
        return self

    async def __aexit__(self, *exc) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        if self.is_temp:
            with contextlib.suppress(OSError):
                self.path.unlink()

    def read_bytes(self) -> bytes:
        return self.path.read_bytes()

    def to_data_url(self) -> str:
        return f"data:{self.mime};base64,{base64.b64encode(self.read_bytes()).decode()}"


class InputResolver:
    def __init__(self, settings: Settings,
                 http_client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient):
        self._settings = settings
        self._client_factory = http_client_factory

    async def resolve(self, src: str) -> MediaInput:
        if urlparse(src).scheme in ("http", "https"):
            return await self._from_url(src)
        return self._from_path(src)

    def check_access(self, path: Path) -> Path:
        """Return the resolved path, or raise if it is outside ``allowed_dirs``."""
        resolved = Path(path).expanduser().resolve()
        allowed = [d.expanduser().resolve() for d in self._settings.allowed_dirs]
        if allowed and not any(resolved.is_relative_to(d) for d in allowed):
            raise AccessDeniedError(
                f"{resolved} is outside the allowed directories: "
                + ", ".join(str(d) for d in allowed))
        return resolved

    def _from_path(self, src: str) -> MediaInput:
        path = self.check_access(Path(src))
        if not path.is_file():
            raise InputNotFoundError(f"File not found: {path}")
        return MediaInput(path, _guess_mime(path.name), path.stat().st_size)

    async def _from_url(self, url: str) -> MediaInput:
        limit = self._settings.max_download_mb * 1024 * 1024
        name = Path(unquote(urlparse(url).path)).name
        tmp_path: Path | None = None
        try:
            async with self._client_factory(follow_redirects=True, timeout=60) as client:
                async with client.stream("GET", url) as resp:
                    if resp.status_code >= 400:
                        raise DownloadError(f"Download failed ({resp.status_code}): {url}")
                    suffix = Path(name).suffix or (
                        mimetypes.guess_extension(
                            resp.headers.get("content-type", "").split(";")[0].strip()) or "")
                    fd, tmp_name = tempfile.mkstemp(suffix=suffix, prefix="mymcps-dl-")
                    tmp_path = Path(tmp_name)
                    size = 0
                    with os.fdopen(fd, "wb") as fh:
                        async for chunk in resp.aiter_bytes():
                            size += len(chunk)
                            if size > limit:
                                raise DownloadError(
                                    f"Download exceeds {self._settings.max_download_mb} MB: {url}")
                            fh.write(chunk)
        except DownloadError:
            _unlink(tmp_path)
            raise
        except httpx.HTTPError as exc:
            _unlink(tmp_path)
            raise DownloadError(f"Download failed: {exc}") from exc
        return MediaInput(tmp_path, _guess_mime(tmp_path.name), size, is_temp=True)


def _guess_mime(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def _unlink(path: Path | None) -> None:
    if path is not None:
        with contextlib.suppress(OSError):
            path.unlink()

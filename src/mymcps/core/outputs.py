"""Where results are written, and how they are returned to the agent."""

from __future__ import annotations

import io
import secrets
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from mcp.server.mcpserver import Image
from PIL import Image as PILImage

from .config import Settings


class OutputManager:
    def __init__(self, settings: Settings, server_name: str,
                 access_checker: Callable[[Path], Path] | None = None):
        self._settings = settings
        self._server = server_name
        self._check = access_checker or (lambda p: p.expanduser().resolve())

    def directory(self, override: str | None = None) -> Path:
        section = self._settings.section(self._server)
        chosen = (override or section.output_dir or self._settings.output_dir)
        path = Path(chosen) if chosen else Path(tempfile.gettempdir()) / "mymcps" / self._server
        path = self._check(path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save(self, data: bytes, ext: str, prefix: str = "out",
             override_dir: str | None = None) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        name = f"{prefix}-{stamp}-{secrets.token_hex(3)}.{ext.lstrip('.')}"
        path = self.directory(override_dir) / name
        path.write_bytes(data)
        return path

    @staticmethod
    def thumbnail(source: Path | bytes, max_side: int = 512) -> Image:
        """JPEG thumbnail the agent can actually look at."""
        raw = source if isinstance(source, bytes) else Path(source).read_bytes()
        with PILImage.open(io.BytesIO(raw)) as img:
            img = img.convert("RGB")
            img.thumbnail((max_side, max_side))
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=85)
        return Image(data=buf.getvalue(), format="jpeg")

    def image_result(self, paths: list[Path], max_side: int = 512) -> list:
        """Text listing the saved paths, followed by one thumbnail per image."""
        text = "Saved:\n" + "\n".join(str(p) for p in paths)
        return [text, *(self.thumbnail(p, max_side) for p in paths)]

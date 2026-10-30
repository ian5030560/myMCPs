"""Where results are written, and how they are returned to the agent."""

from __future__ import annotations

import io
import secrets
import tempfile
from datetime import datetime
from pathlib import Path

from mcp.server.mcpserver import Image
from PIL import Image as PILImage

from .config import Settings
from .errors import AccessDeniedError


class OutputManager:
    def __init__(self, settings: Settings, server_name: str):
        self._settings = settings
        self._server = server_name

    def base_directory(self) -> Path:
        """The configured output folder: the server's section, else the global value, else temp."""
        section = self._settings.section(self._server)
        chosen = section.output_dir or self._settings.output_dir
        path = Path(chosen) if chosen else Path(tempfile.gettempdir()) / "mymcps" / self._server
        return path.expanduser().resolve()

    def validate(self, subfolder: str | None) -> None:
        """Raise if ``subfolder`` is not allowed. Tools call this *before* paying for a model call,
        so a bad ``output_dir`` argument costs nothing. Creates nothing."""
        self._resolve(subfolder)

    def directory(self, subfolder: str | None = None) -> Path:
        """The folder to write into; ``subfolder`` is a tool argument chosen by the agent."""
        path = self._resolve(subfolder)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _resolve(self, subfolder: str | None) -> Path:
        """The agent may only pick a subfolder *inside* the configured output folder, so the
        server never writes elsewhere. Moving results is left to the agent's own file tools."""
        base = self.base_directory()
        path = base
        if subfolder:
            wanted = Path(subfolder)
            if wanted.anchor:  # absolute, rooted ("/x"), or drive-relative ("C:x")
                raise AccessDeniedError(
                    "output_dir must be a relative path inside the output folder, "
                    f"got '{subfolder}'.")
            path = (base / wanted).resolve()
            if not path.is_relative_to(base):
                raise AccessDeniedError(
                    f"output_dir '{subfolder}' escapes the output folder; "
                    "use a plain subfolder name.")
        return path

    def save(self, data: bytes, ext: str, prefix: str = "out",
             subfolder: str | None = None) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        name = f"{prefix}-{stamp}-{secrets.token_hex(3)}.{ext.lstrip('.')}"
        path = self.directory(subfolder) / name
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

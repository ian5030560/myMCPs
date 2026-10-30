"""Turn a LiteLLM ``ImageResponse`` into saved files."""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

from PIL import Image

from mymcps.core.errors import ProviderError
from mymcps.core.inputs import InputResolver
from mymcps.core.outputs import OutputManager

_EXT = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp", "GIF": "gif"}


def _field(obj: Any, name: str) -> Any:
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


class ImageResultReader:
    def __init__(self, inputs: InputResolver, outputs: OutputManager):
        self._inputs = inputs
        self._outputs = outputs

    async def read(self, response: Any) -> list[bytes]:
        """Image bytes in the response (base64 inline, or downloaded from a URL)."""
        images: list[bytes] = []
        for item in _field(response, "data") or []:
            b64 = _field(item, "b64_json")
            url = _field(item, "url")
            if b64:
                images.append(base64.b64decode(b64))
            elif url:
                images.append(await self._inputs.read_bytes(url))
        if not images:
            raise ProviderError(
                "The model returned no image (it may have been blocked by a content filter).")
        return images

    @staticmethod
    def ext_of(data: bytes) -> str:
        try:
            with Image.open(io.BytesIO(data)) as img:
                return _EXT.get(img.format or "", "png")
        except OSError:
            return "png"

    def save_bytes(self, images: list[bytes], prefix: str, output_dir: str | None) -> list[Path]:
        return [self._outputs.save(data, self.ext_of(data), prefix, output_dir) for data in images]

    async def save(self, response: Any, prefix: str, output_dir: str | None = None) -> list[Path]:
        return self.save_bytes(await self.read(response), prefix, output_dir)

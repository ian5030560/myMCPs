"""Turn the images a model returned into bytes and saved files."""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image

from mymcps.core.errors import ProviderError
from mymcps.core.inputs import InputResolver
from mymcps.core.outputs import OutputManager
from mymcps.core.responses import GeneratedImage

_EXT = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp", "GIF": "gif"}


class ImageResultReader:
    def __init__(self, inputs: InputResolver, outputs: OutputManager):
        self._inputs = inputs
        self._outputs = outputs

    async def read(self, results: list[GeneratedImage]) -> list[bytes]:
        """Image bytes (base64 inline, or downloaded from a URL)."""
        images: list[bytes] = []
        for item in results:
            if item.b64:
                images.append(base64.b64decode(item.b64))
            elif item.url:
                images.append(await self._inputs.read_bytes(item.url))
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

    async def save(self, results: list[GeneratedImage], prefix: str,
                   output_dir: str | None = None) -> list[Path]:
        return self.save_bytes(await self.read(results), prefix, output_dir)

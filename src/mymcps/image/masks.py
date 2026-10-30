"""Mask handling.

mymcps convention (documented in the tool descriptions): **white = area to edit, black = keep**.
Providers disagree, so this class converts to whatever each one expects.
"""

from __future__ import annotations

import io

from PIL import Image, ImageFilter

from mymcps.core.errors import InputError


class Mask:
    def __init__(self, gray: Image.Image):
        self._gray = gray  # mode "L", white = edit

    @classmethod
    def load(cls, data: bytes, size: tuple[int, int]) -> Mask:
        """Decode any image into an "L" mask, resized to ``size`` (the original image's size)."""
        try:
            with Image.open(io.BytesIO(data)) as img:
                if img.mode in ("RGBA", "LA"):
                    # flatten transparency onto black so alpha-only masks still work
                    background = Image.new("RGBA", img.size, (0, 0, 0, 255))
                    img = Image.alpha_composite(background, img.convert("RGBA"))
                gray = img.convert("L")
        except OSError as exc:
            raise InputError(f"Mask is not a readable image: {exc}") from exc
        if gray.size != size:
            gray = gray.resize(size, Image.Resampling.BILINEAR)
        return cls(gray)

    @property
    def size(self) -> tuple[int, int]:
        return self._gray.size

    def to_openai_png(self) -> bytes:
        """OpenAI edits the *transparent* pixels, so white (edit) becomes alpha 0."""
        alpha = self._gray.point(lambda v: 255 - v)
        rgba = Image.new("RGBA", self._gray.size, (0, 0, 0, 0))
        rgba.putalpha(alpha)
        return _png(rgba)

    def to_stability_png(self) -> bytes:
        """Stability also edits the white area, so the grayscale mask is used as-is."""
        return _png(self._gray)

    def to_visible_png(self) -> bytes:
        """RGB black/white picture for models that are shown the mask as a normal image."""
        return _png(self._gray.convert("RGB"))

    def composite(self, original: bytes, edited: bytes, feather: int = 4) -> bytes:
        """Paste ``edited`` over ``original`` only where the mask is white.

        With ``feather=0`` every pixel outside the mask is identical to the original.
        """
        with Image.open(io.BytesIO(original)) as o, Image.open(io.BytesIO(edited)) as e:
            base = o.convert("RGB")
            new = e.convert("RGB")
        if new.size != base.size:
            new = new.resize(base.size, Image.Resampling.LANCZOS)
        mask = self._gray
        if mask.size != base.size:
            mask = mask.resize(base.size, Image.Resampling.BILINEAR)
        if feather > 0:
            mask = mask.filter(ImageFilter.GaussianBlur(feather))
        return _png(Image.composite(new, base, mask))


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def image_size(data: bytes) -> tuple[int, int]:
    try:
        with Image.open(io.BytesIO(data)) as img:
            return img.size
    except OSError as exc:
        raise InputError(f"Input is not a readable image: {exc}") from exc

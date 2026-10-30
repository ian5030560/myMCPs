"""Instruction-based editing, optional mask (inpainting) and extra reference images."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from mymcps.core.context import AppContext
from mymcps.core.errors import UnsupportedCapabilityError

from .masks import Mask, image_size
from .results import ImageResultReader

_GEMINI_MASK_NOTE = (
    "The second image is a black-and-white mask of the first image. "
    "Change ONLY the area that is white in the mask; keep everything else exactly as it is. "
)


class ImageEditor:
    def __init__(self, ctx: AppContext):
        self._ctx = ctx
        self._reader = ImageResultReader(ctx.inputs, ctx.outputs)

    async def edit(self, image: str, prompt: str, *, mask: str | None = None,
                   references: list[str] | None = None, model: str | None = None,
                   n: int = 1, size: str | None = None,
                   output_dir: str | None = None) -> list[Path]:
        self._ctx.outputs.validate(output_dir)      # before the paid call, not after it
        resolved = self._ctx.models.resolve("edit", model)
        original = await self._ctx.inputs.read_bytes(image)
        refs = [await self._ctx.inputs.read_bytes(r) for r in references or []]
        mask_obj = None
        if mask:
            mask_obj = Mask.load(await self._ctx.inputs.read_bytes(mask), image_size(original))

        vendor = resolved.vendor
        if vendor == "gemini":
            images = await self._gemini(resolved, original, prompt, mask_obj, refs, n, size)
        elif vendor == "stability":
            images = await self._stability(resolved, original, prompt, mask_obj, refs, n, size)
        else:
            images = await self._openai_style(resolved, original, prompt, mask_obj, refs, n, size)
        return self._reader.save_bytes(images, "edit", output_dir)

    # ── one path per vendor ──────────────────────────────────────────────
    async def _openai_style(self, resolved, original, prompt, mask, refs, n, size) -> list[bytes]:
        if mask is not None and resolved.vendor not in ("openai", "azure"):
            raise UnsupportedCapabilityError(
                f"{resolved.model} does not support masks through mymcps. "
                "Use an openai/... model, or a stability/... or gemini/... model.")
        kw = self._common(n, size)
        if mask is not None:
            kw["mask"] = mask.to_openai_png()
        response = await self._ctx.llm.edit_image(resolved, [original, *refs], prompt, **kw)
        return await self._reader.read(response)

    async def _gemini(self, resolved, original, prompt, mask, refs, n, size) -> list[bytes]:
        """Gemini has no mask parameter: show it the mask, then paste the result back locally."""
        kw = self._common(n, size)
        if mask is None:
            response = await self._ctx.llm.edit_image(resolved, [original, *refs], prompt, **kw)
            return await self._reader.read(response)
        kw.pop("n", None)
        results: list[bytes] = []
        for _ in range(n):
            response = await self._ctx.llm.edit_image(
                resolved, [original, mask.to_visible_png(), *refs],
                _GEMINI_MASK_NOTE + prompt, **kw)
            results.extend(mask.composite(original, data)
                           for data in await self._reader.read(response))
        return results

    async def _stability(self, resolved, original, prompt, mask, refs, n, size) -> list[bytes]:
        if refs:
            raise UnsupportedCapabilityError(
                "Stability edits one image at a time, so reference images are not supported. "
                "Use an openai/... or gemini/... model for that.")
        if mask is None:
            raise UnsupportedCapabilityError(
                "Stability edit_image needs a mask (it inpaints). Without a mask use an "
                "openai/... or gemini/... model, or the stability_edit tool "
                "(search_and_replace, erase, remove_background, ...).")
        inpaint = dataclasses.replace(resolved, model="stability/inpaint")
        kw = {"mask": mask.to_stability_png(), "drop_params": True}
        results: list[bytes] = []
        for _ in range(n):
            response = await self._ctx.llm.edit_image(inpaint, original, prompt, **kw)
            results.extend(await self._reader.read(response))
        return results

    @staticmethod
    def _common(n: int, size: str | None) -> dict:
        kw: dict = {"drop_params": True}
        if n > 1:
            kw["n"] = n
        if size:
            kw["size"] = size
        return kw

"""Text-to-image."""

from __future__ import annotations

from pathlib import Path

from mymcps.core.context import AppContext

from .results import ImageResultReader


class ImageGenerator:
    def __init__(self, ctx: AppContext):
        self._ctx = ctx
        self._reader = ImageResultReader(ctx.inputs, ctx.outputs)

    async def generate(self, prompt: str, *, model: str | None = None, n: int = 1,
                       size: str | None = None, quality: str | None = None,
                       output_dir: str | None = None) -> list[Path]:
        self._ctx.outputs.validate(output_dir)      # before the paid call, not after it
        resolved = self._ctx.models.resolve("gen", model)
        params = {k: v for k, v in {"size": size, "quality": quality}.items() if v}
        # Vendors ignore what they do not support instead of failing the whole call.
        params["drop_params"] = True

        # LiteLLM's Stability adapter returns one image per request: ask n times.
        calls, per_call = (n, 1) if resolved.vendor == "stability" else (1, n)
        images: list[bytes] = []
        for _ in range(calls):
            kw = dict(params)
            if per_call > 1:
                kw["n"] = per_call
            response = await self._ctx.llm.generate_image(resolved, prompt, **kw)
            images.extend(await self._reader.read(response))
        return self._reader.save_bytes(images, "img", output_dir)

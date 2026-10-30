"""Stability AI's one-endpoint-per-operation editing API, behind a single ``stability_edit`` tool.

Not offered: ``style``/``style-transfer`` (LiteLLM routes style-transfer to the wrong endpoint),
``replace-background-and-relight`` (needs fields LiteLLM does not forward), ``creative`` upscale
(asynchronous on Stability's side) and ``sketch``/``structure``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mymcps.core.context import AppContext
from mymcps.core.errors import MediaToolError

from .masks import Mask, image_size
from .results import ImageResultReader

DIRECTIONS = ("left", "right", "top", "bottom")


@dataclass(frozen=True)
class StabilityOperation:
    name: str
    model: str
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    require_any: tuple[str, ...] = ()   # at least one of these must be set (> 0)
    summary: str = ""

    @property
    def accepted(self) -> tuple[str, ...]:
        return self.required + self.optional + self.require_any


OPERATIONS: dict[str, StabilityOperation] = {op.name: op for op in (
    StabilityOperation("remove_background", "stability/remove-background",
                       summary="Cut out the subject on a transparent background."),
    StabilityOperation("erase", "stability/erase", optional=("mask", "grow_mask"),
                       summary="Remove the objects under the mask (white = remove)."),
    StabilityOperation("outpaint", "stability/outpaint", optional=("prompt", "creativity"),
                       require_any=DIRECTIONS,
                       summary="Extend the image by N pixels left/right/top/bottom."),
    StabilityOperation("search_and_replace", "stability/search-and-replace",
                       required=("prompt", "search_prompt"), optional=("negative_prompt",),
                       summary="Replace the object described by search_prompt with prompt."),
    StabilityOperation("search_and_recolor", "stability/search-and-recolor",
                       required=("prompt", "select_prompt"), optional=("negative_prompt",),
                       summary="Recolor the object described by select_prompt as in prompt."),
    StabilityOperation("upscale_fast", "stability/fast",
                       summary="Fast upscale."),
    StabilityOperation("upscale_conservative", "stability/conservative",
                       required=("prompt",), optional=("negative_prompt", "creativity"),
                       summary="Upscale while keeping the content faithful."),
)}


class StabilityEditor:
    def __init__(self, ctx: AppContext):
        self._ctx = ctx
        self._reader = ImageResultReader(ctx.inputs, ctx.outputs)

    @staticmethod
    def available(ctx: AppContext) -> bool:
        """Only offer the tool when a key is reachable for ``stability/...`` models: one on the
        provider they resolve to, or the standard environment variable."""
        probe = ctx.models.resolve_model(next(iter(OPERATIONS.values())).model)
        return ctx.models.has_key(probe)

    async def run(self, operation: str, image: str, *, prompt: str | None = None,
                  mask: str | None = None, search_prompt: str | None = None,
                  select_prompt: str | None = None, left: int = 0, right: int = 0,
                  top: int = 0, bottom: int = 0, creativity: float | None = None,
                  grow_mask: int | None = None, negative_prompt: str | None = None,
                  output_dir: str | None = None) -> list[Path]:
        op = OPERATIONS.get(operation)
        if op is None:
            raise MediaToolError(
                f"Unknown operation '{operation}'. Choose one of: {', '.join(OPERATIONS)}.")
        given = {"prompt": prompt, "mask": mask, "search_prompt": search_prompt,
                 "select_prompt": select_prompt, "creativity": creativity,
                 "grow_mask": grow_mask, "negative_prompt": negative_prompt,
                 "left": left, "right": right, "top": top, "bottom": bottom}
        missing = [name for name in op.required if not given[name]]
        if missing:
            raise MediaToolError(
                f"'{operation}' needs: {', '.join(op.required)} (missing: {', '.join(missing)}).")
        if op.require_any and not any(given[name] for name in op.require_any):
            raise MediaToolError(
                f"'{operation}' needs at least one of {', '.join(op.require_any)} to be > 0 "
                "(pixels to extend).")

        original = await self._ctx.inputs.read_bytes(image)
        kwargs: dict = {"drop_params": True}
        for name in op.accepted:
            value = given[name]
            if name == "prompt" or not value:
                continue
            if name == "mask":
                mask_bytes = await self._ctx.inputs.read_bytes(mask)
                kwargs["mask"] = Mask.load(mask_bytes, image_size(original)).to_stability_png()
            else:
                kwargs[name] = value

        response = await self._ctx.llm.edit_image(
            self._ctx.models.resolve_model(op.model), original,
            prompt if "prompt" in op.accepted and prompt else "", **kwargs)
        return await self._reader.save(response, f"stab-{operation}", output_dir)

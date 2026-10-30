from __future__ import annotations

from typing import Literal

from mymcps.core.abilities import PRODUCES_IMAGES
from mymcps.core.server import BaseMediaServer
from mymcps.core.spec import Purpose, ServerSpec

from .editor import ImageEditor
from .generator import ImageGenerator
from .stability import OPERATIONS, StabilityEditor

# Module level: MCPServer resolves the (string) annotations against this module's globals.
Operation = Literal[tuple(OPERATIONS)]  # type: ignore[valid-type]

_MASK_RULE = ("Mask rule: a black-and-white image the same shape as `image`; "
              "WHITE = area to change, BLACK = keep.")


class ImageServer(BaseMediaServer):
    spec = ServerSpec("image", purposes=(
        Purpose("gen", "text-to-image generation (generate_image)", PRODUCES_IMAGES),
        Purpose("edit", "image editing and inpainting (edit_image)", PRODUCES_IMAGES),
    ))
    instructions = (
        "Generate and edit images. Images are saved to disk; each tool returns the file paths "
        "and a small preview. `image`, `mask` and `references` are local paths or http(s) URLs. "
        "`model` is an alias from list_models or a LiteLLM string such as openai/gpt-image-2, "
        "gemini/gemini-3.1-flash-image or stability/sd3.5-large.")
    default_port = 8701

    def register_tools(self) -> None:
        ctx = self.ctx
        generator, editor = ImageGenerator(ctx), ImageEditor(ctx)
        outputs = ctx.outputs

        @self.mcp.tool()
        async def generate_image(prompt: str, model: str | None = None, n: int = 1,
                                 size: str | None = None, quality: str | None = None,
                                 output_dir: str | None = None) -> list:
            """Generate image(s) from a text prompt.

            Args:
                prompt: What to draw.
                model: Model alias or LiteLLM string. Defaults to the configured image model.
                n: How many images.
                size: e.g. "1024x1024", "1536x1024", "1024x1536" (models ignore sizes they lack).
                quality: e.g. "low", "medium", "high" (ignored by models without it).
                output_dir: Optional subfolder (relative name, e.g. "logos") inside the configured
                    output folder. Absolute paths and ".." are rejected.
            """
            paths = await generator.generate(prompt, model=model, n=n, size=size,
                                             quality=quality, output_dir=output_dir)
            return outputs.image_result(paths)

        @self.mcp.tool()
        async def edit_image(image: str, prompt: str, mask: str | None = None,
                             references: list[str] | None = None, model: str | None = None,
                             n: int = 1, size: str | None = None,
                             output_dir: str | None = None) -> list:
            """Edit an image with an instruction; optionally only inside a mask.

            Without `mask` the model decides what to change. With `mask` only the white area is
            changed (openai/ and stability/ natively; gemini/ is simulated and the result is pasted
            back so pixels outside the mask are untouched).
            References (extra images, e.g. a product to place into the scene) work with openai/
            and gemini/ models, not stability/. stability/ models need a mask here; for other
            Stability operations use stability_edit.

            Args:
                image: Image to edit (path or URL).
                prompt: What to change.
                mask: Optional mask (path or URL): a black-and-white image the same shape as
                    `image`; WHITE = area to change, BLACK = keep.
                references: Optional extra images the prompt can refer to.
                model: Model alias or LiteLLM string.
                n: How many variants.
                size: Output size, e.g. "1024x1024" (ignored where unsupported).
                output_dir: Optional subfolder (relative name, e.g. "logos") inside the configured
                    output folder. Absolute paths and ".." are rejected.
            """
            paths = await editor.edit(image, prompt, mask=mask, references=references,
                                      model=model, n=n, size=size, output_dir=output_dir)
            return outputs.image_result(paths)

        if StabilityEditor.available(ctx):
            self._register_stability(StabilityEditor(ctx))

    def _register_stability(self, stability: StabilityEditor) -> None:
        outputs = self.ctx.outputs
        listing = "\n".join(
            f"                - {op.name}: {op.summary}" for op in OPERATIONS.values())

        async def stability_edit(operation: Operation, image: str, prompt: str | None = None,
                                 mask: str | None = None, search_prompt: str | None = None,
                                 select_prompt: str | None = None, left: int = 0,
                                 right: int = 0, top: int = 0, bottom: int = 0,
                                 creativity: float | None = None, grow_mask: int | None = None,
                                 negative_prompt: str | None = None,
                                 output_dir: str | None = None) -> list:
            paths = await stability.run(
                operation, image, prompt=prompt, mask=mask, search_prompt=search_prompt,
                select_prompt=select_prompt, left=left, right=right, top=top, bottom=bottom,
                creativity=creativity, grow_mask=grow_mask, negative_prompt=negative_prompt,
                output_dir=output_dir)
            return outputs.image_result(paths)

        stability_edit.__doc__ = f"""Stability AI image operations (one image in, one image out).

            Operations:
{listing}

            Required per operation: search_and_replace = prompt + search_prompt;
            search_and_recolor = prompt + select_prompt; upscale_conservative = prompt;
            outpaint = at least one of left/right/top/bottom (pixels to extend).
            Parameters an operation does not use are ignored.

            Args:
                operation: One of the operations above.
                image: Image (path or URL).
                prompt: Describes the desired result (replacement, new color, outpaint content).
                mask: Optional for erase. {_MASK_RULE}
                search_prompt: What to find, for search_and_replace.
                select_prompt: What to recolor, for search_and_recolor.
                left, right, top, bottom: Pixels to extend, for outpaint.
                creativity: How much freedom the model gets (outpaint, upscale_conservative).
                grow_mask: Pixels to grow the erase mask by.
                negative_prompt: What to avoid.
                output_dir: Optional subfolder (relative name, e.g. "logos") inside the configured
                    output folder. Absolute paths and ".." are rejected.
            """
        self.mcp.tool()(stability_edit)


main = ImageServer.main

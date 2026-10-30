import io

import pytest
from PIL import Image

from conftest import image_response, png_bytes
from mymcps.core.errors import UnsupportedCapabilityError
from mymcps.image.editor import ImageEditor


async def test_openai_gets_image_references_and_converted_mask(
        ctx, fake_litellm, photo, mask_file, tmp_path):
    ref = tmp_path / "ref.png"
    ref.write_bytes(png_bytes((10, 10), "green"))
    fake_litellm.response = image_response(png_bytes())
    await ImageEditor(ctx).edit(str(photo), "add a hat", mask=str(mask_file),
                                references=[str(ref)], size="1024x1024")
    name, kw = fake_litellm.calls[0]
    assert name == "aimage_edit" and kw["model"] == "openai/gpt-image-2"
    assert kw["prompt"] == "add a hat" and kw["size"] == "1024x1024"
    assert len(kw["image"]) == 2 and kw["image"][0] == photo.read_bytes()
    mask_png = Image.open(io.BytesIO(kw["mask"]))
    assert mask_png.mode == "RGBA" and mask_png.getpixel((5, 5))[3] == 0   # white -> transparent


async def test_edit_without_mask_sends_no_mask(ctx, fake_litellm, photo):
    fake_litellm.response = image_response(png_bytes())
    await ImageEditor(ctx).edit(str(photo), "make it night")
    assert "mask" not in fake_litellm.calls[0][1]


async def test_gemini_without_mask_edits_directly(ctx, fake_litellm, photo):
    fake_litellm.response = image_response(png_bytes())
    await ImageEditor(ctx).edit(str(photo), "make it night", model="gemini/gemini-3.1-flash-image")
    kw = fake_litellm.calls[0][1]
    assert "mask" not in kw and kw["prompt"] == "make it night"


async def test_gemini_mask_is_simulated_and_pasted_back(ctx, fake_litellm, photo, mask_file):
    # Gemini "repaints everything" red; only the masked (left) half may change in the result.
    fake_litellm.response = image_response(png_bytes((64, 48), "red"))
    paths = await ImageEditor(ctx).edit(
        str(photo), "add a hat", mask=str(mask_file), model="gemini/gemini-3.1-flash-image")
    kw = fake_litellm.calls[0][1]
    assert "mask" not in kw                                   # Gemini has no mask parameter
    assert len(kw["image"]) == 2                              # original + visible mask picture
    assert kw["prompt"].startswith("The second image is a black-and-white mask")
    assert kw["prompt"].endswith("add a hat")
    result = Image.open(paths[0]).convert("RGB")
    assert result.getpixel((50, 24)) == (0, 0, 255)           # outside the mask: original blue
    assert result.getpixel((5, 24))[0] > 200                  # inside the mask: edited red


async def test_gemini_mask_with_n_calls_once_per_variant(ctx, fake_litellm, photo, mask_file):
    fake_litellm.response = image_response(png_bytes())
    paths = await ImageEditor(ctx).edit(str(photo), "x", mask=str(mask_file),
                                        model="gemini/gemini-3.1-flash-image", n=2)
    assert len(fake_litellm.calls) == 2 and len(paths) == 2


async def test_stability_with_mask_uses_inpaint(ctx, fake_litellm, photo, mask_file):
    fake_litellm.response = image_response(png_bytes())
    await ImageEditor(ctx).edit(str(photo), "add a hat", mask=str(mask_file),
                                model="stability/sd3.5-large")
    kw = fake_litellm.calls[0][1]
    assert kw["model"] == "stability/inpaint"
    assert Image.open(io.BytesIO(kw["mask"])).mode == "L"


async def test_stability_rejects_references_and_missing_mask(ctx, fake_litellm, photo, mask_file):
    editor = ImageEditor(ctx)
    with pytest.raises(UnsupportedCapabilityError, match="reference"):
        await editor.edit(str(photo), "x", mask=str(mask_file), references=[str(photo)],
                          model="stability/sd3.5-large")
    with pytest.raises(UnsupportedCapabilityError, match="needs a mask"):
        await editor.edit(str(photo), "x", model="stability/sd3.5-large")
    assert fake_litellm.calls == []


async def test_mask_on_unsupported_provider(ctx, fake_litellm, photo, mask_file):
    with pytest.raises(UnsupportedCapabilityError, match="masks"):
        await ImageEditor(ctx).edit(str(photo), "x", mask=str(mask_file),
                                    model="black_forest_labs/flux-kontext-pro")


async def test_a_bad_output_dir_is_rejected_before_any_model_call(ctx, fake_litellm, photo):
    from mymcps.core.errors import AccessDeniedError

    with pytest.raises(AccessDeniedError):
        await ImageEditor(ctx).edit(str(photo), "x", output_dir="../elsewhere")
    assert fake_litellm.calls == []

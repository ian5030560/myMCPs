import io

import pytest
from PIL import Image

from conftest import png_bytes
from mymcps.core.errors import InputError
from mymcps.image.masks import Mask, image_size


def half_mask(size=(64, 48)) -> bytes:
    img = Image.new("L", size, 0)
    img.paste(255, (0, 0, size[0] // 2, size[1]))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_openai_png_makes_white_area_transparent():
    out = Image.open(io.BytesIO(Mask.load(half_mask(), (64, 48)).to_openai_png()))
    assert out.mode == "RGBA" and out.size == (64, 48)
    assert out.getpixel((5, 5))[3] == 0        # white (edit) -> transparent
    assert out.getpixel((60, 5))[3] == 255     # black (keep) -> opaque


def test_stability_png_keeps_white_as_edit():
    out = Image.open(io.BytesIO(Mask.load(half_mask(), (64, 48)).to_stability_png()))
    assert out.mode == "L" and out.getpixel((5, 5)) == 255 and out.getpixel((60, 5)) == 0


def test_mask_is_resized_to_the_original():
    mask = Mask.load(half_mask((128, 96)), (64, 48))
    assert mask.size == (64, 48)


def test_fully_transparent_rgba_mask_is_flattened_on_black():
    img = Image.new("RGBA", (8, 8), (255, 255, 255, 0))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    out = Image.open(io.BytesIO(Mask.load(buf.getvalue(), (8, 8)).to_stability_png()))
    assert out.getpixel((0, 0)) == 0


def test_composite_without_feather_leaves_outside_pixels_identical():
    original = png_bytes((64, 48), "blue")
    edited = png_bytes((128, 96), "red")           # different size: must be resized
    result = Image.open(io.BytesIO(Mask.load(half_mask(), (64, 48)).composite(
        original, edited, feather=0)))
    assert result.getpixel((5, 5)) == (255, 0, 0)      # inside mask: new content
    assert result.getpixel((60, 5)) == (0, 0, 255)     # outside mask: untouched
    outside = Image.open(io.BytesIO(original)).convert("RGB").crop((32, 0, 64, 48))
    assert result.crop((32, 0, 64, 48)).tobytes() == outside.tobytes()


def test_composite_with_feather_blends_the_edge():
    result = Image.open(io.BytesIO(Mask.load(half_mask(), (64, 48)).composite(
        png_bytes((64, 48), "blue"), png_bytes((64, 48), "red"), feather=4)))
    r, _, b = result.getpixel((32, 24))
    assert 0 < r < 255 and 0 < b < 255


def test_bad_inputs():
    with pytest.raises(InputError):
        Mask.load(b"not an image", (8, 8))
    with pytest.raises(InputError):
        image_size(b"not an image")

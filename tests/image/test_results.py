import base64
import io

import httpx
import pytest
import respx
from PIL import Image

from conftest import image_response, png_bytes
from mymcps.core.errors import ProviderError
from mymcps.image.results import ImageResultReader


@pytest.fixture
def reader(ctx):
    return ImageResultReader(ctx.inputs, ctx.outputs)


async def test_reads_base64_and_dict_responses(reader):
    data = png_bytes()
    assert await reader.read(image_response(data, data)) == [data, data]
    assert await reader.read({"data": [{"b64_json": base64.b64encode(data).decode()}]}) == [data]


@respx.mock
async def test_reads_url_responses(reader):
    data = png_bytes()
    respx.get("https://img.test/a.png").mock(return_value=httpx.Response(200, content=data))
    assert await reader.read(image_response("https://img.test/a.png")) == [data]


async def test_empty_response_is_a_provider_error(reader):
    with pytest.raises(ProviderError, match="no image"):
        await reader.read(image_response())


def test_ext_of(reader):
    buf = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buf, "JPEG")
    assert reader.ext_of(buf.getvalue()) == "jpg"
    assert reader.ext_of(png_bytes()) == "png"
    assert reader.ext_of(b"garbage") == "png"


async def test_save_writes_files(reader, ctx):
    paths = await reader.save(image_response(png_bytes(), png_bytes()), "img")
    assert len(paths) == 2 and all(p.exists() and p.suffix == ".png" for p in paths)
    assert paths[0].parent == ctx.outputs.directory()

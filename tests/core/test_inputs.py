import httpx
import pytest
import respx

from mymcps.core.config import Settings
from mymcps.core.errors import AccessDeniedError, DownloadError, InputNotFoundError
from mymcps.core.inputs import InputResolver


async def test_local_file(tmp_path):
    f = tmp_path / "a.m4a"
    f.write_bytes(b"123")
    async with await InputResolver(Settings()).resolve(str(f)) as inp:
        assert inp.path == f.resolve() and inp.size == 3 and inp.mime == "audio/mp4"
        assert inp.to_data_url().startswith("data:audio/mp4;base64,")
    assert f.exists()  # local files are never deleted


async def test_missing_file(tmp_path):
    with pytest.raises(InputNotFoundError):
        await InputResolver(Settings()).resolve(str(tmp_path / "no.mp4"))


async def test_allowed_dirs(tmp_path):
    ok = tmp_path / "ok"
    ok.mkdir()
    (ok / "a.png").write_bytes(b"x")
    (tmp_path / "b.png").write_bytes(b"x")
    r = InputResolver(Settings(allowed_dirs=[ok]))
    await r.resolve(str(ok / "a.png"))
    with pytest.raises(AccessDeniedError):
        await r.resolve(str(tmp_path / "b.png"))
    with pytest.raises(AccessDeniedError):
        await r.resolve(str(ok / ".." / "b.png"))  # traversal


@respx.mock
async def test_url_download_and_cleanup():
    respx.get("https://h.test/dir/clip.mp4").mock(
        return_value=httpx.Response(200, content=b"video-bytes"))
    async with await InputResolver(Settings()).resolve("https://h.test/dir/clip.mp4") as inp:
        path = inp.path
        assert inp.is_temp and path.suffix == ".mp4" and path.read_bytes() == b"video-bytes"
        assert inp.mime == "video/mp4"
    assert not path.exists()


@respx.mock
async def test_url_content_type_extension():
    respx.get("https://h.test/get").mock(
        return_value=httpx.Response(200, content=b"x", headers={"content-type": "audio/mpeg"}))
    inp = await InputResolver(Settings()).resolve("https://h.test/get")
    assert inp.path.suffix in (".mp3", ".mpga", ".mp2")
    inp.cleanup()


@respx.mock
async def test_url_too_large_and_http_error():
    respx.get("https://h.test/big").mock(return_value=httpx.Response(200, content=b"x" * 2_000_000))
    with pytest.raises(DownloadError, match="exceeds 1 MB"):
        await InputResolver(Settings(max_download_mb=1)).resolve("https://h.test/big")
    respx.get("https://h.test/404").mock(return_value=httpx.Response(404))
    with pytest.raises(DownloadError, match="404"):
        await InputResolver(Settings()).resolve("https://h.test/404")

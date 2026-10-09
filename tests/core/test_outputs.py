import io
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from mymcps.core.config import Settings
from mymcps.core.errors import AccessDeniedError
from mymcps.core.inputs import InputResolver
from mymcps.core.outputs import OutputManager


def png(size=(1000, 500)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "red").save(buf, "PNG")
    return buf.getvalue()


def test_default_dir_is_system_temp():
    d = OutputManager(Settings(), "image_gen").directory()
    assert d == Path(tempfile.gettempdir()) / "mymcps" / "image_gen" and d.is_dir()


def test_priority_override_section_global(tmp_path):
    s = Settings(output_dir=str(tmp_path / "g"), image_gen={"output_dir": str(tmp_path / "s")})
    m = OutputManager(s, "image_gen")
    assert m.directory() == (tmp_path / "s").resolve()
    assert m.directory(str(tmp_path / "o")) == (tmp_path / "o").resolve()
    assert OutputManager(s, "video_watch").directory() == (tmp_path / "g").resolve()


def test_save_names_and_content(settings):
    m = OutputManager(settings, "image_gen")
    a, b = m.save(b"1", "png", "img"), m.save(b"2", ".png", "img")
    assert a != b and a.name.startswith("img-") and a.suffix == ".png"
    assert a.read_bytes() == b"1"


def test_thumbnail_is_resized_jpeg():
    img = OutputManager.thumbnail(png(), max_side=256)
    assert img._format == "jpeg"
    with Image.open(io.BytesIO(img.data)) as t:
        assert t.size == (256, 128)


def test_image_result(settings):
    m = OutputManager(settings, "image_gen")
    paths = [m.save(png((64, 64)), "png")]
    out = m.image_result(paths)
    assert str(paths[0]) in out[0] and len(out) == 2


def test_writes_respect_allowed_dirs(tmp_path):
    s = Settings(allowed_dirs=[tmp_path / "ok"], output_dir=str(tmp_path / "elsewhere"))
    m = OutputManager(s, "image_gen", InputResolver(s).check_access)
    with pytest.raises(AccessDeniedError):
        m.directory()
    assert m.directory(str(tmp_path / "ok" / "sub")).is_dir()

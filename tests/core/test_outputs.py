import io
import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from mymcps.core.config import Settings
from mymcps.core.errors import AccessDeniedError
from mymcps.core.outputs import OutputManager


def png(size=(1000, 500)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "red").save(buf, "PNG")
    return buf.getvalue()


def test_default_dir_is_system_temp():
    d = OutputManager(Settings(), "image").directory()
    assert d == Path(tempfile.gettempdir()) / "mymcps" / "image" and d.is_dir()


def test_priority_section_then_global(tmp_path):
    s = Settings(output_dir=str(tmp_path / "g"),
                 sections={"image": {"output_dir": str(tmp_path / "s")}})
    assert OutputManager(s, "image").directory() == (tmp_path / "s").resolve()
    assert OutputManager(s, "video").directory() == (tmp_path / "g").resolve()


def test_subfolder_is_created_inside_the_output_folder(settings, tmp_path):
    m = OutputManager(settings, "image")
    assert m.directory("logos") == (tmp_path / "out" / "logos").resolve()
    assert m.directory("a/b") == (tmp_path / "out" / "a" / "b").resolve()
    assert m.directory("a/../c") == (tmp_path / "out" / "c").resolve()   # stays inside
    assert m.directory("") == (tmp_path / "out").resolve()
    assert m.directory(None) == (tmp_path / "out").resolve()
    assert (tmp_path / "out" / "a" / "b").is_dir()


def test_save_into_a_subfolder(settings, tmp_path):
    path = OutputManager(settings, "image").save(b"x", "png", "img", "shots")
    assert path.parent == (tmp_path / "out" / "shots").resolve() and path.read_bytes() == b"x"


@pytest.mark.parametrize("bad", ["..", "../x", "a/../../x", "a/../.."])
def test_subfolder_may_not_escape_the_output_folder(settings, tmp_path, bad):
    with pytest.raises(AccessDeniedError, match="escapes"):
        OutputManager(settings, "image").directory(bad)
    assert not (tmp_path / "x").exists()


def test_subfolder_may_not_be_absolute(settings, tmp_path):
    for bad in (str(tmp_path / "elsewhere"), "/elsewhere"):
        with pytest.raises(AccessDeniedError, match="relative"):
            OutputManager(settings, "image").directory(bad)
    assert not (tmp_path / "elsewhere").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="drive-relative paths only exist on Windows")
def test_subfolder_may_not_be_drive_relative(settings):
    with pytest.raises(AccessDeniedError, match="relative"):
        OutputManager(settings, "image").directory("C:foo")


def test_save_names_and_content(settings):
    m = OutputManager(settings, "image")
    a, b = m.save(b"1", "png", "img"), m.save(b"2", ".png", "img")
    assert a != b and a.name.startswith("img-") and a.suffix == ".png"
    assert a.read_bytes() == b"1"


def test_thumbnail_is_resized_jpeg():
    img = OutputManager.thumbnail(png(), max_side=256)
    assert img._format == "jpeg"
    with Image.open(io.BytesIO(img.data)) as t:
        assert t.size == (256, 128)


def test_image_result(settings):
    m = OutputManager(settings, "image")
    paths = [m.save(png((64, 64)), "png")]
    out = m.image_result(paths)
    assert str(paths[0]) in out[0] and len(out) == 2


def test_variables_are_never_expanded_in_the_output_dir_argument(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    folder = OutputManager(settings, "image").directory("${OPENAI_API_KEY}")
    assert folder.name == "${OPENAI_API_KEY}" and "sk-secret" not in str(folder)
    assert OutputManager(settings, "image").directory("~").name == "~"


def test_validate_rejects_a_bad_subfolder_and_creates_nothing(settings, tmp_path):
    outputs = OutputManager(settings, "image")
    for bad in ("../x", str(tmp_path.resolve())):
        with pytest.raises(AccessDeniedError):
            outputs.validate(bad)
    outputs.validate("fine")
    outputs.validate(None)
    assert not (tmp_path / "out").exists()

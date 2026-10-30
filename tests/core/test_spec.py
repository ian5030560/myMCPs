from importlib.metadata import entry_points

import pytest

from mymcps.core.server import BaseMediaServer
from mymcps.core.spec import Purpose, ServerSpec

GROUP = "mymcps.servers"


def registered_servers():
    return {ep.name: ep.load() for ep in entry_points(group=GROUP)}


@pytest.mark.parametrize("name", ["image", "video", "audio", "media-convert", "a1", "x-y-2"])
def test_valid_server_names(name):
    assert ServerSpec(name).name == name


@pytest.mark.parametrize("name", [
    "", "Image", "my_server", "1image", "-image", "image gen", "image.gen", "bild!"])
def test_invalid_server_names_are_rejected(name):
    with pytest.raises(ValueError, match="Invalid server name"):
        ServerSpec(name)


@pytest.mark.parametrize("name", ["", "Gen", "1gen", "gen-x", "gen model"])
def test_invalid_purpose_names_are_rejected(name):
    with pytest.raises(ValueError, match="Invalid purpose name"):
        Purpose(name, "x")


def test_a_purpose_is_configured_as_name_underscore_model():
    assert Purpose("gen", "x").field == "gen_model"
    assert Purpose("transcribe", "x").field == "transcribe_model"


def test_duplicate_purposes_are_rejected():
    with pytest.raises(ValueError, match="twice"):
        ServerSpec("demo", purposes=(Purpose("a", "x"), Purpose("a", "y")))


def test_unknown_purpose_lookup_lists_the_declared_ones():
    spec = ServerSpec("demo", purposes=(Purpose("a", "x"),))
    with pytest.raises(KeyError, match="declared: a"):
        spec.purpose("b")


def test_the_command_is_mymcps_plus_the_name():
    assert ServerSpec("media-convert").command == "mymcps-media-convert"


def test_every_registered_server_has_a_valid_unique_name():
    servers = registered_servers()
    assert {"image", "video", "audio"} <= set(servers)
    names = [cls.spec.name for cls in servers.values()]
    assert len(names) == len(set(names)), f"duplicate server names: {names}"
    for entry_name, cls in servers.items():
        assert issubclass(cls, BaseMediaServer)
        assert cls.spec.name == entry_name, "entry point name must equal the server's name"


def test_registered_servers_use_distinct_http_ports():
    ports = [cls.default_port for cls in registered_servers().values()]
    assert len(ports) == len(set(ports))


@pytest.mark.parametrize("name,fields", [
    ("image", ["gen_model", "edit_model"]),
    ("video", ["watch_model"]),
    ("audio", ["listen_model", "transcribe_model"]),
])
def test_each_server_declares_its_purposes(name, fields):
    spec = registered_servers()[name].spec
    assert [p.field for p in spec.purposes] == fields

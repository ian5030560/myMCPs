"""A server that declares no purposes touches nothing model-related."""

import subprocess
import sys
import textwrap

import pytest
from mcp import Client

from mymcps.core.config import SettingsLoader
from mymcps.core.errors import ConfigError
from mymcps.core.server import BaseMediaServer
from mymcps.core.spec import Purpose, ServerSpec

PLAIN = ServerSpec("plain")
WITH_MODELS = ServerSpec("modelful", purposes=(Purpose("main", "the main job"),))
KNOWN = {"plain", "modelful", "image"}

BROKEN_MODEL_CONFIG = """
[providers.p]
vendor = "openai"
bogus_field = 1
api_base = "${UNDEFINED_VARIABLE}"

[models.m]
model = "openai/x"
provider = "nope"
"""


class PlainServer(BaseMediaServer):
    spec = PLAIN

    def register_tools(self) -> None:
        @self.mcp.tool()
        def ping() -> str:
            """Say pong."""
            return "pong"


@pytest.fixture
def config(tmp_path):
    def write(text):
        path = tmp_path / "config.toml"
        path.write_text(text, encoding="utf-8")
        return path
    return write


def load(server, path):
    return SettingsLoader(server, path, environ={}, known_servers=KNOWN).load()


# ── tools ────────────────────────────────────────────────────────────────


async def test_a_server_without_purposes_offers_no_list_models(make_ctx):
    async with Client(PlainServer(make_ctx(server=PLAIN)).mcp) as client:
        names = {tool.name for tool in (await client.list_tools()).tools}
    assert names == {"ping"}


async def test_a_server_with_purposes_still_offers_list_models(make_ctx):
    class Modelful(PlainServer):
        spec = WITH_MODELS

    async with Client(Modelful(make_ctx(server=WITH_MODELS)).mcp) as client:
        names = {tool.name for tool in (await client.list_tools()).tools}
    assert names == {"ping", "list_models"}


# ── configuration ────────────────────────────────────────────────────────


def test_broken_providers_and_aliases_do_not_stop_a_server_without_purposes(config):
    settings = load(PLAIN, config(BROKEN_MODEL_CONFIG))
    assert settings.providers == {} and settings.models == {}


@pytest.mark.parametrize("text,needle", [
    ("[providers.p]\nvendor = 'openai'\nbogus_field = 1\n", "bogus_field"),
    ("[providers.p]\nvendor = 'openai'\napi_base = '${UNDEFINED_VARIABLE}'\n",
     "UNDEFINED_VARIABLE"),
    ("[models.m]\nmodel = 'openai/x'\nprovider = 'nope'\n", "`nope`"),
])
def test_each_kind_of_breakage_stops_a_server_that_uses_models_but_not_one_without(
        config, text, needle):
    path = config(text)
    with pytest.raises(ConfigError, match=needle):
        load(WITH_MODELS, path)
    load(PLAIN, path)


def test_it_still_validates_the_top_level_settings(config):
    with pytest.raises(ConfigError) as err:
        load(PLAIN, config("allowed_dirs = ['x']\nmax_download_mb = 'big'\n"))
    assert len(err.value.problems) == 2


def test_it_still_validates_its_own_section(config):
    with pytest.raises(ConfigError) as err:
        load(PLAIN, config("[plain]\nwatch_model = 'x'\noutput_dir = 'out'\n"))
    [problem] = err.value.problems
    assert "[plain]" in problem and "watch_model" in problem


def test_it_still_expands_variables_in_what_it_reads(config, tmp_path):
    with pytest.raises(ConfigError, match="NOT_SET"):
        load(PLAIN, config("[plain]\noutput_dir = '${NOT_SET}'\n"))
    settings = load(PLAIN, config("output_dir = '${CONFIG_DIR}/out/${SERVER}'\n"))
    assert settings.output_dir.replace("\\", "/").endswith("/out/plain")


def test_it_reads_its_output_folder_and_keeps_other_sections_out_of_the_way(config):
    settings = load(PLAIN, config("[plain]\noutput_dir = 'mine'\n[modelful]\nmain_model = 5\n"))
    assert settings.section("plain").output_dir is not None


def test_the_project_layer_of_a_server_without_models_ignores_them_too(config, tmp_path):
    project = tmp_path / "project.toml"
    project.write_text("output_dir = 'out'\n[models.m]\nmodel = 'x'\napi_base = 'y'\n",
                       encoding="utf-8")
    settings = SettingsLoader(PLAIN, environ={}, known_servers=KNOWN,
                              project_path=project).load()
    assert settings.output_dir is not None and settings.models == {}


# ── no LiteLLM ───────────────────────────────────────────────────────────


def test_starting_a_server_without_purposes_does_not_import_litellm(config):
    path = config(BROKEN_MODEL_CONFIG + "\n[plain]\noutput_dir = 'out'\n")
    code = textwrap.dedent(f"""
        import sys
        from mymcps.core.server import BaseMediaServer
        from mymcps.core.spec import ServerSpec

        class Plain(BaseMediaServer):
            spec = ServerSpec("plain")
            def register_tools(self):
                pass
            def run(self, **kw):
                self.started = True

        Plain.main(["--config", {str(path)!r}])
        sys.exit(1 if "litellm" in sys.modules else 0)
    """)
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""

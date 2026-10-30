"""Layered config files: shared file, server file, project layer.

Same seam as test_config: file texts plus an environment dictionary plus a server declaration,
through to loaded settings and resolved models.
"""

import logging
from pathlib import Path

import pytest

from mymcps.core.config import SettingsLoader
from mymcps.core.errors import ConfigError
from mymcps.core.models import ModelRegistry
from mymcps.core.outputs import OutputManager
from mymcps.core.spec import Purpose, ServerSpec

IMAGE = ServerSpec("image", purposes=(Purpose("gen", "generate"), Purpose("edit", "edit")))
VIDEO = ServerSpec("video", purposes=(Purpose("watch", "watch"),))
KNOWN = {"image", "video", "audio"}


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A fake home with an empty ~/.mymcps; also keeps the real one out of the tests."""
    folder = tmp_path / "home"
    (folder / ".mymcps").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: folder)
    return folder / ".mymcps"


@pytest.fixture
def project(tmp_path):
    folder = tmp_path / "proj" / ".mymcps"
    folder.mkdir(parents=True)
    return folder


class Loaded:
    def __init__(self, settings, models):
        self.settings = settings
        self.models = models


@pytest.fixture
def load(llm):
    def _load(server=IMAGE, *, config=None, project=None, environ=None):
        settings = SettingsLoader(server, config, environ=environ or {}, known_servers=KNOWN,
                                  project_path=project).load()
        return Loaded(settings, ModelRegistry(settings, llm, server))
    return _load


@pytest.fixture
def problems(load):
    def _problems(**kw):
        with pytest.raises(ConfigError) as err:
            load(**kw)
        return err.value.problems
    return _problems


def write(folder: Path, name: str, text: str) -> Path:
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


# ── the global layer: shared file + server file ──────────────────────────


def test_the_server_file_is_layered_over_the_shared_file(home, load):
    write(home, "config.toml", "[image]\ngen_model = 'shared/gen'\nedit_model = 'shared/edit'\n")
    write(home, "image.toml", "[image]\ngen_model = 'server/gen'\n")
    models = load().models
    assert models.resolve("gen").model == "server/gen"
    assert models.resolve("edit").model == "shared/edit"      # sections merge field by field


def test_a_server_file_applies_to_its_own_server_only(home, load):
    write(home, "config.toml", "[image]\ngen_model = 'a/b'\n[video]\nwatch_model = 'c/d'\n")
    write(home, "video.toml", "[video]\nwatch_model = 'video/only'\n")
    assert load(IMAGE).models.resolve("gen").model == "a/b"
    assert load(VIDEO).models.resolve("watch").model == "video/only"


def test_both_files_are_optional_at_their_default_location(home, load):
    assert load().settings.sources == []
    write(home, "image.toml", "[image]\ngen_model = 'a/b'\n")
    assert load().models.resolve("gen").model == "a/b"            # a server file alone is enough
    (home / "image.toml").unlink()
    write(home, "config.toml", "[image]\ngen_model = 'c/d'\n")
    assert load().models.resolve("gen").model == "c/d"


def test_a_named_config_is_the_whole_global_layer_and_no_server_file_is_loaded(
        home, load, tmp_path):
    write(home, "image.toml", "[image]\ngen_model = 'server/gen'\n")
    named = write(tmp_path, "named.toml", "[image]\nedit_model = 'named/edit'\n")
    loaded = load(config=named)
    assert loaded.settings.sources == [("shared", str(named))]
    with pytest.raises(Exception, match="gen_model"):
        loaded.models.resolve("gen")


def test_a_config_named_by_the_environment_is_also_alone(home, tmp_path, llm):
    write(home, "image.toml", "[image]\ngen_model = 'server/gen'\n")
    named = write(tmp_path, "named.toml", "[image]\nedit_model = 'named/edit'\n")
    settings = SettingsLoader(IMAGE, environ={"MYMCPS_CONFIG": str(named)},
                              known_servers=KNOWN).load()
    assert [kind for kind, _ in settings.sources] == ["shared"]


def test_the_shared_file_may_hold_other_servers_sections_but_a_server_file_may_not(
        home, problems):
    write(home, "image.toml", "[image]\ngen_model = 'a/b'\n[video]\nwatch_model = 'c/d'\n")
    [problem] = problems()
    assert str(home / "image.toml") in problem and "[video]" in problem
    assert "own server's section" in problem


def test_a_server_file_with_an_unknown_section_fails(home, problems):
    write(home, "image.toml", "[imgae]\ngen_model = 'a/b'\n")
    [problem] = problems()
    assert "[imgae]" in problem and "unknown section" in problem


def test_a_server_file_may_hold_top_level_settings_providers_and_models(home, load):
    write(home, "image.toml", """
output_dir = 'mine'
[providers.local]
vendor = 'openai'
api_base = 'http://x/v1'
[models.q]
model = 'openai/qwen'
provider = 'local'
[image]
gen_model = 'q'
""")
    loaded = load()
    assert loaded.models.resolve("gen").call_kwargs() == {"api_base": "http://x/v1"}
    assert loaded.settings.output_dir == str((home / "mine").resolve())


# ── the project layer ────────────────────────────────────────────────────


def test_the_project_layer_is_loaded_only_when_named(home, project, load, tmp_path, monkeypatch):
    write(project, "image.toml", "[image]\ngen_model = 'proj/gen'\n")
    monkeypatch.chdir(project.parent)
    assert load().settings.sources == []                  # nothing is discovered automatically
    named = load(project=project / "image.toml")
    assert named.models.resolve("gen").model == "proj/gen"
    assert named.settings.sources == [("project", str(project / "image.toml"))]


def test_a_missing_project_file_fails_startup(home, problems, tmp_path):
    missing = tmp_path / "nope.toml"
    [problem] = problems(project=missing)
    assert str(missing) in problem and "--project-config" in problem


def test_merge_order_is_shared_then_server_then_project(home, project, load):
    shared = (home.parent / "shared").as_posix()
    write(home, "config.toml", f"max_download_mb = 1\noutput_dir = '{shared}'\n"
          "[image]\ngen_model = 'shared/g'\nedit_model = 'shared/e'\n")
    write(home, "image.toml", "max_download_mb = 2\n[image]\ngen_model = 'server/g'\n")
    write(project, "image.toml", "[image]\nedit_model = 'project/e'\n")
    loaded = load(project=project / "image.toml")
    assert loaded.settings.max_download_mb == 2             # project does not set it; server wins
    assert Path(loaded.settings.output_dir) == Path(shared)
    assert loaded.models.resolve("gen").model == "server/g"
    assert loaded.models.resolve("edit").model == "project/e"
    assert [kind for kind, _ in loaded.settings.sources] == ["shared", "server", "project"]


def test_models_and_providers_merge_by_name_with_the_whole_entry_replaced(home, project, load):
    write(home, "config.toml", """
[providers.local]
vendor = 'openai'
api_base = 'http://shared/v1'
api_key = 'shared-key'
[providers.local.extra]
timeout = 1
[models.q]
model = 'openai/one'
provider = 'local'
[models.q.extra]
retries = 3
[models.keep]
model = 'openai/keep'
""")
    write(home, "image.toml", """
[providers.local]
vendor = 'openai'
api_base = 'http://server/v1'
[models.q]
model = 'openai/two'
provider = 'local'
""")
    loaded = load()
    kwargs = loaded.models.resolve_model("q").call_kwargs()
    assert kwargs == {"api_base": "http://server/v1"}       # nothing of the old entries is left
    assert loaded.models.resolve_model("q").model == "openai/two"
    assert loaded.models.resolve_model("keep").model == "openai/keep"


def test_a_replaced_provider_forgets_the_key_variable_of_the_one_it_replaces(home, load):
    write(home, "config.toml", "[providers.local]\nvendor='openai'\napi_key='${UNSET_ONE}'\n"
          "[models.q]\nmodel='openai/x'\nprovider='local'\n")
    assert load().settings.key_variables == {"local": "UNSET_ONE"}
    write(home, "image.toml", "[providers.local]\nvendor='openai'\napi_key='literal'\n")
    loaded = load()
    assert loaded.settings.key_variables == {}
    assert loaded.models.resolve_model("q").call_kwargs()["api_key"] == "literal"


def test_the_project_layer_can_link_an_alias_to_a_global_provider(home, project, load):
    write(home, "config.toml", "[providers.local]\nvendor='openai'\napi_base='http://x/v1'\n"
          "api_key='k'\n")
    write(project, "image.toml", "[models.q]\nmodel='openai/qwen'\nprovider='local'\n"
          "[image]\ngen_model='q'\n")
    q = load(project=project / "image.toml").models.resolve("gen")
    assert q.call_kwargs() == {"api_base": "http://x/v1", "api_key": "k"}


def test_a_link_from_the_project_layer_to_an_undefined_provider_names_the_project_file(
        home, project, problems):
    write(project, "image.toml", "[models.q]\nmodel='openai/qwen'\nprovider='nope'\n")
    [problem] = problems(project=project / "image.toml")
    assert str(project / "image.toml") in problem and "`nope`" in problem


@pytest.mark.parametrize("text,field", [
    ("[providers.p]\nvendor = 'openai'\n", "providers"),
    ("max_download_mb = 5\n", "max_download_mb"),
])
def test_the_project_layer_cannot_hold_providers_or_download_limits(
        home, project, problems, text, field):
    write(project, "image.toml", text)
    [problem] = problems(project=project / "image.toml")
    assert field in problem and "project layer" in problem


@pytest.mark.parametrize("field", ["api_base", "api_key", "extra", "vendor"])
def test_project_aliases_may_set_only_the_model_and_a_provider_link(
        home, project, problems, field):
    value = "{}" if field == "extra" else "'x'"
    write(project, "image.toml", f"[models.q]\nmodel = 'openai/x'\n{field} = {value}\n")
    [problem] = problems(project=project / "image.toml")
    assert "[models.q]" in problem and field in problem and "project layer" in problem


def test_an_unknown_field_in_a_project_alias_is_an_ordinary_unknown_field(
        home, project, problems):
    write(project, "image.toml", "[models.q]\nmodel = 'openai/x'\nmodle = 'y'\n")
    [problem] = problems(project=project / "image.toml")
    assert "modle" in problem and "unknown field" in problem


def test_the_project_layer_holds_only_its_servers_section(home, project, problems):
    write(project, "image.toml", "[image]\ngen_model='a/b'\n[video]\nwatch_model='c/d'\n")
    [problem] = problems(project=project / "image.toml")
    assert "[video]" in problem and "own server's section" in problem


def test_the_project_layer_can_set_models_and_output_folders(home, project, load, tmp_path):
    write(project, "image.toml", "output_dir = 'results'\n[image]\ngen_model='a/b'\n"
          "output_dir = 'images'\n")
    s = load(project=project / "image.toml").settings
    assert s.output_dir == str((project / "results").resolve())
    assert s.section("image").output_dir == str((project / "images").resolve())


# ── project layer variables ──────────────────────────────────────────────


def test_the_project_layer_expands_builtin_variables(home, project, load):
    write(project, "image.toml", "output_dir = '${CONFIG_DIR}/out/${SERVER}'\n")
    out = load(project=project / "image.toml").settings.output_dir
    assert out.replace("\\", "/") == str(project.resolve()).replace("\\", "/") + "/out/image"


def test_the_project_layer_never_expands_environment_variables(home, project, problems):
    write(project, "image.toml", "output_dir = '/data/${SECRET_TOKEN}'\n")
    [problem] = problems(project=project / "image.toml", environ={"SECRET_TOKEN": "hunter2"})
    assert "SECRET_TOKEN" in problem and "built-in" in problem
    assert "hunter2" not in problem


def test_a_builtin_name_set_in_the_environment_is_still_the_builtin(home, project, load):
    write(project, "image.toml", "output_dir = '/x/${SERVER}'\n")
    out = load(project=project / "image.toml", environ={"SERVER": "evil"}).settings.output_dir
    assert out.replace("\\", "/").endswith("/x/image")


def test_environment_variables_still_work_in_the_global_layer(home, load):
    write(home, "config.toml", "output_dir = '/data/${WHERE}'\n")
    assert load(environ={"WHERE": "here"}).settings.output_dir.replace("\\", "/").endswith(
        "/data/here")


# ── paths and output folder ──────────────────────────────────────────────


def test_relative_paths_are_relative_to_the_file_they_are_written_in(home, project, load):
    write(home, "config.toml", "output_dir = 'shared-out'\n")
    write(home, "image.toml", "[image]\noutput_dir = 'server-out'\n")
    s = load().settings
    assert s.output_dir == str((home / "shared-out").resolve())
    assert s.section("image").output_dir == str((home / "server-out").resolve())


def test_the_sections_output_dir_beats_the_top_level_one_whichever_layer_set_it(
        home, project, load, tmp_path):
    write(home, "config.toml", "[image]\noutput_dir = '/from/section'\n")
    write(project, "image.toml", "output_dir = '/from/project/top'\n")
    settings = load(project=project / "image.toml").settings
    base = OutputManager(settings, "image").base_directory()
    assert base == Path("/from/section").resolve()


def test_output_folder_falls_back_to_the_top_level_then_temp(home, load):
    import tempfile
    write(home, "config.toml", "output_dir = '/top'\n")
    assert OutputManager(load().settings, "image").base_directory() == Path("/top").resolve()
    (home / "config.toml").unlink()
    assert OutputManager(load().settings, "image").base_directory() == (
        Path(tempfile.gettempdir()) / "mymcps" / "image").resolve()


# ── reporting ────────────────────────────────────────────────────────────


def test_problems_in_every_file_are_reported_together_each_naming_its_own_file(
        home, project, problems):
    write(home, "config.toml", "allowed_dirs = ['x']\n")
    write(home, "image.toml", "[video]\nwatch_model='a/b'\n")
    write(project, "image.toml", "[providers.p]\nvendor='openai'\n")
    found = problems(project=project / "image.toml")
    assert len(found) == 3
    assert any(str(home / "config.toml") in p for p in found)
    assert any(str(home / "image.toml") in p for p in found)
    assert any(str(project / "image.toml") in p for p in found)


def test_an_invalid_file_does_not_hide_the_problems_of_the_others(home, project, problems):
    write(home, "config.toml", "this is = = not toml")
    write(project, "image.toml", "max_download_mb = 5\n")
    found = problems(project=project / "image.toml")
    assert len(found) == 2 and "invalid TOML" in found[0]


# ── startup log ──────────────────────────────────────────────────────────


def test_the_server_logs_each_loaded_file_with_its_layer_and_never_a_value(
        home, project, caplog, capsys, monkeypatch):
    from mymcps.image.server import ImageServer

    write(home, "config.toml",
          "[providers.openai]\napi_key = 'sk-very-secret'\n[image]\ngen_model = 'openai/x'\n")
    write(project, "image.toml", "[image]\nedit_model = 'openai/y'\n")
    monkeypatch.setattr(ImageServer, "run", lambda self, **kw: None)
    with caplog.at_level(logging.INFO, logger="mymcps.core.server"):
        ImageServer.main(["--project-config", str(project / "image.toml")])
    text = caplog.text
    assert f"shared config {home / 'config.toml'}" in text
    assert f"project config {project / 'image.toml'}" in text
    assert "sk-very-secret" not in text and "openai/x" not in text
    assert capsys.readouterr().out == ""

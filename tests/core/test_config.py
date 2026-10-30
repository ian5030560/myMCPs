"""The config seam: config text + environment + a server declaration -> settings and models.

Every test here feeds a config file (and an environment dictionary) to the loader for a given
server and looks only at what comes out: the loaded settings, the model a purpose resolves to,
or the problems that stop the server from starting.
"""

from dataclasses import dataclass
from pathlib import Path

import pytest

from mymcps.core.config import Settings, SettingsLoader
from mymcps.core.errors import ConfigError
from mymcps.core.models import ModelRegistry
from mymcps.core.spec import Purpose, ServerSpec

IMAGE = ServerSpec("image", purposes=(Purpose("gen", "generate"), Purpose("edit", "edit")))
VIDEO = ServerSpec("video", purposes=(Purpose("watch", "watch"),))
KNOWN = {"image", "video", "audio"}

VALID = """
output_dir = "from-toml"

[providers.local]
vendor = "openai"
api_base = "http://x/v1"
api_key = "literal-key"

[models.local-vl]
model = "openai/qwen"
provider = "local"

[models.local-vl.extra]
timeout = 5

[image]
gen_model = "local-vl"
edit_model = "openai/gpt-image-2"
output_dir = "pictures"

[video]
watch_model = "gemini/gemini-2.5-flash"
"""


@dataclass
class Loaded:
    settings: Settings
    models: ModelRegistry
    path: Path


@pytest.fixture
def load(tmp_path, llm):
    """load(text, server=IMAGE, environ=None, known=KNOWN, how="path") -> Loaded.

    ``how`` is how the file is named: "path" (--config) or "env" (MYMCPS_CONFIG).
    """
    def _load(text=VALID, *, server=IMAGE, environ=None, known=KNOWN, how="path"):
        path = tmp_path / "config.toml"
        path.write_text(text, encoding="utf-8")
        env = dict(environ or {})
        if how == "env":
            env[SettingsLoader.ENV_CONFIG] = str(path)
        settings = SettingsLoader(
            server, path if how == "path" else None, environ=env, known_servers=known).load()
        return Loaded(settings, ModelRegistry(settings, llm, server), path)
    return _load


@pytest.fixture
def problems(load):
    """problems(text, **kw) -> the list of problems that stop the server from starting."""
    def _problems(text, **kw):
        with pytest.raises(ConfigError) as err:
            load(text, **kw)
        return err.value.problems
    return _problems


# ── loading ──────────────────────────────────────────────────────────────


def test_a_valid_config_loads_and_a_purpose_resolves_to_its_model(load, tmp_path):
    loaded = load()
    assert loaded.settings.output_dir == str(tmp_path.resolve() / "from-toml")
    resolved = loaded.models.resolve("gen")
    assert resolved.alias == "local-vl" and resolved.model == "openai/qwen"
    assert resolved.call_kwargs() == {
        "timeout": 5, "api_base": "http://x/v1", "api_key": "literal-key"}
    assert loaded.models.resolve("edit").model == "openai/gpt-image-2"


def test_the_servers_own_section_is_loaded(load, tmp_path):
    assert load().settings.section("image").output_dir == str(tmp_path.resolve() / "pictures")


def test_only_the_servers_own_section_is_read(load):
    loaded = load()
    assert set(loaded.settings.sections) == {"image"}
    assert loaded.settings.section("video").output_dir is None


def test_a_server_without_a_section_gets_an_empty_one(load):
    section = load("output_dir = 'x'").settings.section("image")
    assert section.output_dir is None and section.model_for(IMAGE.purpose("gen")) is None


def test_no_config_file_gives_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    s = SettingsLoader(IMAGE, environ={}, known_servers=KNOWN).load()
    assert s.output_dir is None and s.models == {} and s.sections == {}


def test_the_default_location_is_read_when_it_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".mymcps").mkdir()
    (tmp_path / ".mymcps" / "config.toml").write_text("output_dir = 'home'", encoding="utf-8")
    s = SettingsLoader(IMAGE, environ={}, known_servers=KNOWN).load()
    assert s.output_dir == str((tmp_path / ".mymcps" / "home").resolve())


def test_config_path_from_the_environment(load, tmp_path):
    assert load(how="env").settings.output_dir == str(tmp_path.resolve() / "from-toml")


def test_settings_come_only_from_files_not_per_field_environment_variables(load, tmp_path):
    env = {"MYMCPS_OUTPUT_DIR": "from-env", "MYMCPS_ALLOWED_DIRS": "a", "MYMCPS_VIDEO_MODEL": "x",
           "MYMCPS_IMAGE_MODEL": "x", "MYMCPS_AUDIO_MODEL": "x", "MYMCPS_TRANSCRIPTION_MODEL": "x"}
    loaded = load(environ=env)
    assert loaded.settings.output_dir == str(tmp_path.resolve() / "from-toml")
    assert loaded.models.resolve("gen").alias == "local-vl"


def test_passthrough_parameters_are_not_validated(load):
    loaded = load("""
[models.m]
model = "openai/x"
[models.m.extra]
timeout = 3
anything_at_all = { nested = [1, 2, { deeper = true }] }
not_a_known_litellm_option = "yes"
""")
    kwargs = loaded.models.resolve_model("m").call_kwargs()
    assert kwargs["timeout"] == 3 and kwargs["not_a_known_litellm_option"] == "yes"


def test_every_server_of_the_installation_is_a_known_section_by_default(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text("[audio]\nlisten_model = 'x'\n[video]\nwatch_model = 'y'\n", encoding="utf-8")
    # known_servers is not given: the names come from the installed servers' metadata.
    assert SettingsLoader(IMAGE, path, environ={}).load().sections == {}


def test_a_server_that_is_not_registered_still_accepts_its_own_section(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text("[demo]\noutput_dir = 'd'\n", encoding="utf-8")
    demo = ServerSpec("demo")
    section = SettingsLoader(demo, path, environ={}).load().section("demo")
    assert section.output_dir == str(tmp_path.resolve() / "d")


# ── strict validation ────────────────────────────────────────────────────


def test_an_unknown_top_level_field_fails(problems, tmp_path):
    [problem] = problems("allowed_dirs = ['x']")
    assert str(tmp_path / "config.toml") in problem
    assert "allowed_dirs" in problem and "unknown field" in problem


def test_a_typo_in_a_top_level_field_suggests_the_right_one(problems):
    [problem] = problems("output_dr = 'x'")
    assert "output_dr" in problem and "did you mean `output_dir`" in problem


def test_an_unknown_field_in_a_model_alias_fails(problems):
    [problem] = problems("[models.m]\nmodel = 'a'\nprovidr = 'b'")
    assert "[models.m]" in problem and "providr" in problem
    assert "did you mean `provider`" in problem


def test_a_model_alias_without_a_model_fails(problems):
    [problem] = problems("[models.m]\nprovider = 'x'")
    assert "[models.m]" in problem and "model" in problem and "required" in problem


def test_an_unknown_field_in_the_servers_own_section_fails(problems):
    [problem] = problems("[image]\ngen_modle = 'x'")
    assert "[image]" in problem and "gen_modle" in problem
    assert "did you mean `gen_model`" in problem


def test_a_model_field_the_server_does_not_declare_fails(problems):
    [problem] = problems("[image]\nwatch_model = 'x'")
    assert "[image]" in problem and "watch_model" in problem
    assert "gen_model" in problem and "edit_model" in problem   # what it does declare
    assert "no `watch` job" in problem
    assert "did you mean" not in problem    # a valid field of another server is not a typo


def test_the_old_default_model_field_fails(problems):
    [problem] = problems("[image]\ndefault_model = 'x'")
    assert "default_model" in problem and "unknown field" in problem


def test_a_section_that_is_not_a_known_server_fails(problems):
    [problem] = problems("[imgae]\ngen_model = 'x'")
    assert "[imgae]" in problem and "unknown section" in problem
    assert "did you mean [image]" in problem


def test_an_old_server_name_is_an_unknown_section(problems):
    [problem] = problems("[image_gen]\ndefault_model = 'x'")
    assert "[image_gen]" in problem and "unknown section" in problem


def test_wrong_types_fail_and_name_the_field(problems):
    found = problems("max_download_mb = 'big'\n[image]\ngen_model = 5")
    joined = "\n".join(found)
    assert len(found) == 2
    assert "max_download_mb" in joined and "[image]" in joined and "gen_model" in joined


def test_models_must_be_a_table_of_aliases(problems):
    [problem] = problems("models = 5")
    assert "models" in problem


def test_invalid_toml_names_the_file(problems, tmp_path):
    [problem] = problems("this is = = not toml")
    assert str(tmp_path / "config.toml") in problem and "invalid TOML" in problem


# ── another server's section ─────────────────────────────────────────────


def test_a_mistake_inside_another_servers_section_does_not_stop_this_server(load):
    loaded = load("[image]\ngen_model = 'a'\n[video]\nwatch_modle = 'oops'\nbogus = 1\n")
    assert loaded.models.resolve("gen").model == "a"


def test_another_servers_values_are_not_even_type_checked(load):
    assert load("[video]\nwatch_model = 5\n").settings.section("video").output_dir is None


def test_the_same_mistake_stops_the_server_it_belongs_to(problems):
    [problem] = problems("[video]\nwatch_modle = 'oops'", server=VIDEO)
    assert "[video]" in problem and "did you mean `watch_model`" in problem


# ── reporting ────────────────────────────────────────────────────────────


def test_all_problems_are_reported_together_each_naming_file_section_and_field(problems, tmp_path):
    found = problems("""
allowed_dirs = ["x"]

[imgae]
gen_model = "a"

[models.m]
model = "a"
bogus = 1

[image]
nope = 1
""")
    assert len(found) == 4
    joined = "\n".join(found)
    for needle in ("allowed_dirs", "[imgae]", "[models.m]", "bogus", "[image]", "nope"):
        assert needle in joined, needle
    assert all(str(tmp_path / "config.toml") in line for line in found)


def test_the_error_message_lists_every_problem(load):
    with pytest.raises(ConfigError) as err:
        load("allowed_dirs = 1\n[imgae]\nx = 1\n")
    assert "allowed_dirs" in str(err.value) and "[imgae]" in str(err.value)


def test_values_from_the_file_are_never_repeated_in_a_message(problems):
    found = problems("""
max_download_mb = "hunter2"
[models.m]
model = "a"
secret_field = "correct-horse"
[providers.p]
api_key = 987654321
""")
    joined = "\n".join(found)
    assert "hunter2" not in joined and "987654321" not in joined
    assert "correct-horse" not in joined
    assert len(found) == 3


# ── naming the file ──────────────────────────────────────────────────────


def test_an_explicit_config_path_that_does_not_exist_fails(tmp_path):
    missing = tmp_path / "nope.toml"
    with pytest.raises(ConfigError) as err:
        SettingsLoader(IMAGE, missing, environ={}, known_servers=KNOWN).load()
    [problem] = err.value.problems
    assert str(missing) in problem and "--config" in problem


def test_a_config_path_from_the_environment_that_does_not_exist_fails(tmp_path):
    missing = tmp_path / "nope.toml"
    env = {SettingsLoader.ENV_CONFIG: str(missing)}
    with pytest.raises(ConfigError) as err:
        SettingsLoader(IMAGE, environ=env, known_servers=KNOWN).load()
    [problem] = err.value.problems
    assert str(missing) in problem and "MYMCPS_CONFIG" in problem


def test_a_config_path_that_is_a_folder_fails(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        SettingsLoader(IMAGE, tmp_path, environ={}, known_servers=KNOWN).load()


# ── the shipped example must stay valid ──────────────────────────────────

EXAMPLE = Path(__file__).resolve().parents[2] / "config.example.toml"


@pytest.mark.parametrize("name", ["image", "video", "audio"])
def test_the_example_config_passes_strict_validation_for_every_server(name):
    from importlib.metadata import entry_points

    server = {ep.name: ep.load() for ep in entry_points(group="mymcps.servers")}[name].spec
    settings = SettingsLoader(server, EXAMPLE, environ={}).load()
    # every purpose of that server is configured by the example
    section = settings.section(name)
    assert all(section.model_for(purpose) for purpose in server.purposes)


# ── providers ────────────────────────────────────────────────────────────


def test_a_literal_key_is_accepted_without_a_warning(load, capsys):
    load("[providers.openai]\napi_key = 'sk-literal'\n")
    assert capsys.readouterr().err == ""


def test_api_key_env_is_no_longer_a_field(problems):
    [problem] = problems("[providers.openai]\napi_key_env = 'X'\n")
    assert "[providers.openai]" in problem and "api_key_env" in problem
    assert "unknown field" in problem and "api_key" in problem


def test_connection_fields_moved_from_the_alias_to_the_provider(problems):
    found = problems("[models.m]\nmodel = 'openai/x'\napi_base = 'http://x'\napi_key = 'k'\n")
    joined = "\n".join(found)
    assert len(found) == 2 and "api_base" in joined and "[models.m]" in joined


def test_an_unknown_field_in_a_provider_fails(problems):
    [problem] = problems("[providers.local]\nvendor = 'openai'\napi_basee = 'x'\n")
    assert "[providers.local]" in problem and "did you mean `api_base`" in problem


def test_a_provider_named_after_a_vendor_applies_to_raw_strings(load):
    loaded = load("[providers.stability]\napi_base = 'http://proxy'\napi_key = 'k'\n")
    resolved = loaded.models.resolve_model("stability/sd3.5-large")
    assert resolved.call_kwargs() == {"api_base": "http://proxy", "api_key": "k"}
    assert loaded.settings.providers["stability"].vendor == "stability"


def test_a_provider_with_another_name_is_not_reached_by_a_raw_string(load):
    loaded = load("[providers.local]\nvendor = 'openai'\napi_base = 'http://x'\n")
    assert loaded.models.resolve_model("openai/gpt-image-2").call_kwargs() == {}


def test_an_explicit_link_beats_the_provider_named_after_the_vendor(load):
    loaded = load("""
[providers.openai]
api_key = "official"
[providers.local]
vendor = "openai"
api_key = "mine"
[models.q]
model = "openai/qwen"
provider = "local"
""")
    assert loaded.models.resolve_model("q").call_kwargs() == {"api_key": "mine"}
    assert loaded.models.resolve_model("openai/x").call_kwargs() == {"api_key": "official"}


def test_a_link_to_an_undefined_provider_fails(problems):
    [problem] = problems("[providers.a]\nvendor = 'openai'\n[models.m]\nmodel = 'openai/x'\n"
                         "provider = 'nope'\n")
    assert "[models.m]" in problem and "provider" in problem and "`nope`" in problem
    assert "defined: a" in problem


def test_a_link_to_a_provider_of_another_vendor_fails(problems):
    [problem] = problems("[providers.local]\nvendor = 'openai'\n"
                         "[models.m]\nmodel = 'gemini/x'\nprovider = 'local'\n")
    assert "[models.m]" in problem and "gemini" in problem and "openai" in problem


def test_a_link_to_a_vendor_named_provider_of_another_vendor_fails(problems):
    [problem] = problems("[providers.stability]\napi_key = 'k'\n"
                         "[models.m]\nmodel = 'openai/x'\nprovider = 'stability'\n")
    assert "[models.m]" in problem and "openai" in problem and "stability" in problem


def test_a_vendor_named_provider_cannot_state_another_vendor(problems):
    [problem] = problems("[providers.stability]\nvendor = 'openai'\n")
    assert "[providers.stability]" in problem and "vendor" in problem


def test_a_providers_vendor_is_taken_from_the_models_that_link_to_it(load):
    loaded = load("[providers.local]\napi_base = 'http://x'\n"
                  "[models.a]\nmodel = 'openai/x'\nprovider = 'local'\n"
                  "[models.b]\nmodel = 'openai/y'\nprovider = 'local'\n")
    assert loaded.settings.providers["local"].vendor == "openai"
    assert loaded.models.resolve_model("a").vendor == "openai"


def test_linked_models_that_disagree_about_the_vendor_fail(problems):
    [problem] = problems("[providers.local]\napi_base = 'http://x'\n"
                         "[models.a]\nmodel = 'openai/x'\nprovider = 'local'\n"
                         "[models.b]\nmodel = 'gemini/y'\nprovider = 'local'\n")
    assert "[providers.local]" in problem and "vendor" in problem
    assert "gemini" in problem and "openai" in problem


def test_a_provider_nothing_links_to_is_harmless(load):
    assert load("[providers.spare]\napi_base = 'http://x'\n").settings.providers["spare"]


def test_passthrough_parameters_merge_provider_first_and_the_model_wins(load):
    loaded = load("""
[providers.local]
vendor = "openai"
[providers.local.extra]
timeout = 5
retries = 2
[models.m]
model = "openai/x"
provider = "local"
[models.m.extra]
timeout = 30
""")
    assert loaded.models.resolve_model("m").call_kwargs() == {"timeout": 30, "retries": 2}


def test_alias_names_with_a_slash_fail(problems):
    [problem] = problems("[models.'openai/x']\nmodel = 'openai/x'\n")
    assert "openai/x" in problem and "`/`" in problem


def test_provider_problems_are_reported_together_with_the_others(problems):
    found = problems("allowed_dirs = 1\n[models.m]\nmodel = 'openai/x'\nprovider = 'nope'\n")
    assert len(found) == 2


def test_another_servers_models_are_not_involved(load):
    # Providers and aliases are shared, so every model server checks them; sections are not.
    assert load("[video]\nwatch_model = 5\n").settings.sections == {}


# ── variables ────────────────────────────────────────────────────────────


def provider_key(loaded):
    return loaded.models.resolve_model("openai/x").provider


def test_variables_expand_in_every_string_including_nested_passthrough(load):
    loaded = load("""
[providers.local]
vendor = "openai"
api_base = "${HOST}/v1"
[providers.local.extra]
headers = { x-tenant = "${TENANT}", list = ["a-${TENANT}"] }
[models.m]
model = "openai/x"
provider = "local"
""", environ={"HOST": "http://h", "TENANT": "t1"})
    kwargs = loaded.models.resolve_model("m").call_kwargs()
    assert kwargs["api_base"] == "http://h/v1"
    assert kwargs["headers"] == {"x-tenant": "t1", "list": ["a-t1"]}


def test_built_in_variables_win_over_environment_variables(load):
    loaded = load("output_dir = '/${SERVER}'", environ={"SERVER": "env"})
    assert loaded.settings.output_dir.replace("\\", "/").endswith("/image")


def test_the_builtins(load, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("tempfile.gettempdir", lambda: "/the/temp")
    loaded = load("[providers.local]\nvendor='openai'\n[providers.local.extra]\n"
                  "a='${CONFIG_DIR}'\nb='${CWD}'\nc='${TEMP}'\nd='${SERVER}'\n"
                  "[models.m]\nmodel='openai/x'\nprovider='local'\n")
    kwargs = loaded.models.resolve_model("m").call_kwargs()
    assert kwargs == {"a": str(tmp_path.resolve()), "b": str(Path.cwd()), "c": "/the/temp",
                      "d": "image"}


def test_server_is_the_name_of_the_server_that_loads_the_file(load):
    text = """
[video]
watch_model = 'x'
[providers.p]
vendor = 'openai'
[providers.p.extra]
n = '${SERVER}'
[models.m]
model = 'openai/x'
provider = 'p'
"""
    assert load(text, server=VIDEO).models.resolve_model("m").extra["n"] == "video"


def test_a_leading_tilde_is_the_home_directory(load, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    loaded = load("""
output_dir = '~/pics'
[image]
output_dir = '~'
""")
    assert Path(loaded.settings.output_dir) == tmp_path / "home" / "pics"
    assert Path(loaded.settings.section("image").output_dir) == tmp_path / "home"

def test_double_dollar_is_a_literal_dollar(load):
    loaded = load("[providers.p]\nvendor='openai'\n[providers.p.extra]\nprice='$$5'\n"
                  "[models.m]\nmodel='openai/x'\nprovider='p'\n")
    assert loaded.models.resolve_model("m").extra["price"] == "$5"


def test_expansion_is_single_pass(load):
    loaded = load("[providers.p]\nvendor='openai'\n[providers.p.extra]\n"
                  "a='${A}'\nb='$${A}'\n[models.m]\nmodel='openai/x'\nprovider='p'\n",
                  environ={"A": "${B}", "B": "boom"})
    extra = loaded.models.resolve_model("m").extra
    assert extra == {"a": "${B}", "b": "${A}"}


def test_an_undefined_variable_fails_naming_file_section_and_field(problems, tmp_path):
    [problem] = problems("[providers.p]\nvendor='openai'\napi_base = 'http://${NOPE}/v1'\n")
    assert str(tmp_path / "config.toml") in problem
    assert "[providers.p]" in problem and "api_base" in problem and "`NOPE`" in problem


def test_undefined_variables_are_all_reported_together(problems):
    found = problems("output_dir = '${A}'\n[image]\ngen_model = '${B}'\n")
    assert len(found) == 2


def test_a_malformed_reference_fails(problems):
    [problem] = problems("output_dir = '${not valid}'")
    assert "output_dir" in problem and "not a valid variable" in problem


def test_another_servers_variables_are_not_expanded(load):
    load("[video]\nwatch_model = '${UNDEFINED}'\n")      # does not stop the image server


def test_values_are_never_echoed_for_undefined_variables(problems):
    found = problems("[providers.p]\nvendor='openai'\napi_base='secret-${NOPE}'\n")
    assert "secret-" not in found[0]


# ── keys ─────────────────────────────────────────────────────────────────


KEY_CONFIG = """
[providers.local]
vendor = "openai"
api_base = "http://x/v1"
api_key = "${LOCAL_API_KEY}"
[models.q]
model = "openai/qwen"
provider = "local"
"""


def test_a_key_variable_with_a_value_is_the_key(load):
    loaded = load(KEY_CONFIG, environ={"LOCAL_API_KEY": "s3cret"})
    assert loaded.models.resolve_model("q").call_kwargs()["api_key"] == "s3cret"
    assert loaded.models.describe()["models"][0]["key_configured"] is True


def test_an_unset_key_variable_means_no_key_and_does_not_stop_startup(load):
    loaded = load(KEY_CONFIG)
    assert "api_key" not in loaded.models.resolve_model("q").call_kwargs()
    [entry] = loaded.models.describe()["models"]
    assert entry["key_configured"] is False


def test_an_unset_key_variable_does_not_fall_back_to_the_vendors_standard_key(load):
    loaded = load(KEY_CONFIG, environ={"OPENAI_API_KEY": "someone-elses"})
    assert loaded.models.describe()["models"][0]["key_configured"] is False
    assert not loaded.models.has_key(loaded.models.resolve_model("q"))


async def test_a_call_that_fails_for_lack_of_a_key_names_the_variable(load, llm, fake_litellm):
    from mymcps.core.errors import AuthError

    class AuthenticationError(Exception):
        pass

    fake_litellm.raises = AuthenticationError("no key")
    loaded = load(KEY_CONFIG)
    with pytest.raises(AuthError, match="LOCAL_API_KEY"):
        await llm.complete(loaded.models.resolve_model("q"), [])


def test_a_literal_key_is_used_as_written_even_with_a_dollar_or_tilde(load):
    loaded = load("[providers.openai]\napi_key = '~abc$$x'\n")
    assert provider_key(loaded).api_key == "~abc$x"


def test_a_malformed_reference_in_a_key_still_fails(problems):
    [problem] = problems("[providers.openai]\napi_key = '${bad name}'\n")
    assert "[providers.openai]" in problem and "api_key" in problem


# ── relative paths ───────────────────────────────────────────────────────


def test_a_relative_output_dir_is_relative_to_the_config_file(load, tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    loaded = load("output_dir = 'results'\n[image]\noutput_dir = 'img'\n")
    assert loaded.settings.output_dir == str(tmp_path.resolve() / "results")
    assert loaded.settings.section("image").output_dir == str(tmp_path.resolve() / "img")


def test_an_absolute_output_dir_is_left_alone(load, tmp_path):
    target = str((tmp_path / "abs").resolve())
    assert load(f"output_dir = '{target}'").settings.output_dir == target


def test_an_empty_output_dir_still_means_the_default(load):
    assert load("output_dir = ''").settings.output_dir in ("", None)


def test_the_config_path_itself_is_used_as_given(tmp_path, monkeypatch):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.toml").write_text("max_download_mb = 7", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    s = SettingsLoader(IMAGE, "sub/c.toml", environ={}, known_servers=KNOWN).load()
    assert s.max_download_mb == 7


def test_config_dir_is_the_folder_of_the_file_the_value_is_written_in(load, tmp_path):
    loaded = load("output_dir = '${CONFIG_DIR}/out'")
    assert loaded.settings.output_dir.replace("\\", "/") == \
        str(tmp_path.resolve()).replace("\\", "/") + "/out"


# ── abilities are derived, not declared ──────────────────────────────────


def test_the_capabilities_field_is_gone(problems):
    [problem] = problems("[models.m]\nmodel = 'openai/x'\ncapabilities = ['vision']\n")
    assert "[models.m]" in problem and "capabilities" in problem and "unknown field" in problem


# ── names from the earlier layout fail loudly and point to the README ─────


@pytest.mark.parametrize("old,new", [
    ("image_gen", "[image]"), ("video_watch", "[video]"), ("audio_listen", "[audio]"),
])
def test_an_old_server_name_says_what_replaced_it(problems, old, new):
    [problem] = problems(f"[{old}]\ndefault_model = 'x'\n")
    assert f"[{old}]" in problem and new in problem and "Migrating" in problem


@pytest.mark.parametrize("text,field,hint", [
    ("allowed_dirs = ['x']", "allowed_dirs", "no longer restrict"),
    ("[image]\ndefault_model = 'x'", "default_model", "gen_model"),
    ("[image]\nimage_model = 'x'", "image_model", "gen_model"),
    ("[audio]\ntranscription_model = 'x'", "transcription_model", "transcribe_model"),
    ("[providers.p]\nvendor='openai'\napi_key_env = 'X'", "api_key_env", "${VAR}"),
    ("[models.m]\nmodel='openai/x'\ncapabilities = []", "capabilities", "derived"),
    ("[models.m]\nmodel='openai/x'\napi_base = 'http://x'", "api_base", "[providers."),
    ("[models.m]\nmodel='openai/x'\napi_key = 'k'", "api_key", "[providers."),
])
def test_an_old_setting_says_what_replaced_it(problems, text, field, hint):
    server = VIDEO if text.startswith("[audio]") else IMAGE
    known = KNOWN | {"audio"}
    [problem] = problems(text, server=ServerSpec("audio", purposes=(
        Purpose("transcribe", "t"),)) if text.startswith("[audio]") else server, known=known)
    assert field in problem and hint in problem and "Migrating" in problem


def test_settings_that_were_never_old_names_do_not_get_the_pointer(problems):
    [problem] = problems("output_dr = 'x'")
    assert "Migrating" not in problem


def test_old_settings_environment_variables_are_reported():
    from mymcps.core.config import legacy_environment

    found = legacy_environment({"MYMCPS_CONFIG": "c", "MYMCPS_OUTPUT_DIR": "x",
                                "MYMCPS_ALLOWED_DIRS": "y", "OTHER": "z"})
    assert found == ["MYMCPS_ALLOWED_DIRS", "MYMCPS_OUTPUT_DIR"]

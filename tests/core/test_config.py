from pathlib import Path

import pytest

from mymcps.core.config import SettingsLoader

TOML = """
output_dir = "from-toml"
[image_gen]
default_model = "toml-image"
[video_watch]
default_model = "toml-video"
[models.local-vl]
model = "openai/qwen"
api_base = "http://x/v1"
capabilities = ["vision"]
[models.local-vl.extra]
timeout = 5
"""


def write(tmp_path: Path, text: str = TOML) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(text, encoding="utf-8")
    return p


def test_no_config_file_gives_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    s = SettingsLoader(environ={}).load()
    assert s.output_dir is None and s.allowed_dirs == [] and s.models == {}


def test_toml_is_loaded(tmp_path):
    s = SettingsLoader(write(tmp_path), environ={}).load()
    assert s.output_dir == "from-toml"
    assert s.image_gen.default_model == "toml-image"
    assert s.models["local-vl"].extra == {"timeout": 5}
    assert s.models["local-vl"].capabilities == ["vision"]


def test_env_overrides_toml(tmp_path):
    env = {"MYMCPS_OUTPUT_DIR": "from-env", "MYMCPS_VIDEO_MODEL": "env-video",
           "MYMCPS_TRANSCRIPTION_MODEL": "env-asr"}
    s = SettingsLoader(write(tmp_path), environ=env).load()
    assert s.output_dir == "from-env"
    assert s.video_watch.default_model == "env-video"
    assert s.audio_listen.transcription_model == "env-asr"
    assert s.image_gen.default_model == "toml-image"  # untouched


def test_allowed_dirs_env(tmp_path):
    import os
    env = {"MYMCPS_ALLOWED_DIRS": os.pathsep.join(["a", "b"])}
    s = SettingsLoader(environ=env, config_path=None).load()
    assert s.allowed_dirs == [Path("a"), Path("b")]


def test_config_path_from_env(tmp_path):
    s = SettingsLoader(environ={"MYMCPS_CONFIG": str(write(tmp_path))}).load()
    assert s.output_dir == "from-toml"


def test_explicit_missing_config_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        SettingsLoader(tmp_path / "nope.toml", environ={}).load()

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters

from mymcps.audio.server import AudioServer
from mymcps.core.context import AppContext
from mymcps.image.server import ImageServer
from mymcps.video.server import VideoServer

SERVERS = [ImageServer, VideoServer, AudioServer]


def installed_command(name: str) -> str | None:
    """Find a console script next to this Python, even if the venv is not activated."""
    path = str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    return shutil.which(name, path=path)


@pytest.mark.parametrize("cls", SERVERS)
def test_parser_defaults(cls):
    args = cls.build_parser().parse_args([])
    assert args.http is False and args.port == cls.default_port and args.host == "127.0.0.1"


def test_distinct_ports():
    assert len({c.default_port for c in SERVERS}) == 3


@pytest.mark.parametrize("cls", SERVERS)
async def test_list_models_in_memory(cls, llm, tmp_path):
    cfg = tmp_path / "empty.toml"          # never read the real ~/.mymcps/config.toml in tests
    cfg.write_text("", encoding="utf-8")
    ctx = AppContext.create(cls.spec, cfg)
    ctx.llm = llm
    async with Client(cls(ctx).mcp) as client:
        tools = await client.list_tools()
        assert "list_models" in [t.name for t in tools.tools]
        result = await client.call_tool("list_models", {})
        assert not result.is_error


@pytest.mark.parametrize("cls", SERVERS)
def test_the_command_is_mymcps_plus_the_name(cls):
    assert cls.spec.command == f"mymcps-{cls.spec.name}"
    assert cls.build_parser().prog == cls.spec.command


@pytest.mark.parametrize("name", ["image", "video", "audio"])
def test_the_installed_commands_exist(name):
    assert installed_command(f"mymcps-{name}") is not None


async def test_stdio_end_to_end_through_the_new_command(tmp_path):
    cfg = tmp_path / "none.toml"
    cfg.write_text("", encoding="utf-8")
    command = installed_command("mymcps-image")
    assert command, "mymcps-image is not installed; run pip install -e ."
    params = StdioServerParameters(
        command=command, args=[],
        env={"MYMCPS_CONFIG": str(cfg), "SYSTEMROOT": "C:\\Windows"})
    async with Client(params) as client:
        tools = await client.list_tools()
        assert "list_models" in [t.name for t in tools.tools]
        res = await client.call_tool("list_models", {})
        assert not res.is_error


# ── a bad config stops the server cleanly ────────────────────────────────

BAD_CONFIG = """
allowed_dirs = ["x"]

[imgae]
gen_model = "a"

[image]
gen_modle = "b"
"""


def test_main_reports_every_problem_on_stderr_and_exits(tmp_path, capsys):
    cfg = tmp_path / "bad.toml"
    cfg.write_text(BAD_CONFIG, encoding="utf-8")
    with pytest.raises(SystemExit) as exit_info:
        ImageServer.main(["--config", str(cfg)])
    captured = capsys.readouterr()
    assert exit_info.value.code == 2
    assert captured.out == ""                      # stdout is the stdio transport
    for needle in ("mymcps-image", "allowed_dirs", "[imgae]", "gen_modle", str(cfg)):
        assert needle in captured.err, needle


def test_a_missing_explicit_config_stops_the_server(tmp_path, capsys):
    with pytest.raises(SystemExit):
        ImageServer.main(["--config", str(tmp_path / "missing.toml")])
    assert "not found" in capsys.readouterr().err


def test_the_real_command_exits_with_a_message_instead_of_a_traceback(tmp_path):
    cfg = tmp_path / "bad.toml"
    cfg.write_text(BAD_CONFIG, encoding="utf-8")
    command = installed_command("mymcps-image")
    assert command, "mymcps-image is not installed; run pip install -e ."
    run = subprocess.run([command, "--config", str(cfg)], capture_output=True, text=True,
                         timeout=60)
    assert run.returncode == 2
    assert run.stdout == ""
    assert "Traceback" not in run.stderr
    assert "[imgae]" in run.stderr and "allowed_dirs" in run.stderr

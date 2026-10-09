import sys

import pytest
from mcp import Client, StdioServerParameters

from mymcps.audio_listen.server import AudioListenServer
from mymcps.core.context import AppContext
from mymcps.image_gen.server import ImageGenServer
from mymcps.video_watch.server import VideoWatchServer

SERVERS = [ImageGenServer, VideoWatchServer, AudioListenServer]


@pytest.mark.parametrize("cls", SERVERS)
def test_parser_defaults(cls):
    args = cls.build_parser().parse_args([])
    assert args.http is False and args.port == cls.default_port and args.host == "127.0.0.1"


def test_distinct_ports():
    assert len({c.default_port for c in SERVERS}) == 3


@pytest.mark.parametrize("cls", SERVERS)
async def test_list_models_in_memory(cls, llm):
    ctx = AppContext.create(cls.name)
    ctx.llm = llm
    async with Client(cls(ctx).mcp) as client:
        tools = await client.list_tools()
        assert [t.name for t in tools.tools] == ["list_models"]
        result = await client.call_tool("list_models", {})
        assert not result.is_error


async def test_stdio_end_to_end(tmp_path):
    cfg = tmp_path / "none.toml"
    cfg.write_text("", encoding="utf-8")
    params = StdioServerParameters(
        command=sys.executable, args=["-c", "from mymcps.image_gen.server import main; main()"],
        env={"MYMCPS_CONFIG": str(cfg), "SYSTEMROOT": "C:\\Windows"})
    async with Client(params) as client:
        tools = await client.list_tools()
        assert "list_models" in [t.name for t in tools.tools]
        res = await client.call_tool("list_models", {})
        assert not res.is_error

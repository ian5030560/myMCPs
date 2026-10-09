"""Base class shared by the three MCP servers."""

from __future__ import annotations

import argparse
import logging
import sys
from abc import ABC, abstractmethod
from typing import Any

from mcp.server.mcpserver import MCPServer

from .context import AppContext


class BaseMediaServer(ABC):
    name: str = ""            # settings section / tool-set name, e.g. "image_gen"
    cli_name: str = ""        # console script name, e.g. "image-gen"
    instructions: str = ""
    default_port: int = 8700

    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.mcp = MCPServer(self.cli_name or self.name, instructions=self.instructions)
        self._register_common_tools()
        self.register_tools()

    @abstractmethod
    def register_tools(self) -> None:
        """Subclasses register their own tools with ``self.mcp.tool()``."""

    def _register_common_tools(self) -> None:
        @self.mcp.tool()
        def list_models() -> list[dict[str, Any]]:
            """List the configured model aliases and the defaults used by this server."""
            return self.ctx.models.describe(self.name)

    def run(self, *, http: bool = False, host: str = "127.0.0.1",
            port: int | None = None) -> None:
        if http:
            self.mcp.run("streamable-http", host=host, port=port or self.default_port)
        else:
            self.mcp.run("stdio")

    @classmethod
    def build_parser(cls) -> argparse.ArgumentParser:
        p = argparse.ArgumentParser(prog=cls.cli_name or cls.name, description=cls.instructions)
        p.add_argument("--http", action="store_true",
                       help="serve Streamable HTTP instead of stdio")
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=cls.default_port)
        p.add_argument("--config", help="path to config.toml")
        return p

    @classmethod
    def main(cls, argv: list[str] | None = None) -> None:
        args = cls.build_parser().parse_args(argv)
        # stdout belongs to the stdio transport: log to stderr only.
        logging.basicConfig(stream=sys.stderr, level=logging.INFO)
        ctx = AppContext.create(cls.name, args.config)
        cls(ctx).run(http=args.http, host=args.host, port=args.port)

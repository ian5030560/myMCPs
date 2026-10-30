"""Base class shared by the three MCP servers."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from mcp.server.mcpserver import MCPServer

from .config import legacy_environment
from .context import AppContext
from .errors import ConfigError
from .spec import ServerSpec

log = logging.getLogger(__name__)


class BaseMediaServer(ABC):
    spec: ClassVar[ServerSpec]   # the server's name and purposes
    instructions: str = ""
    default_port: int = 8700

    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.mcp = MCPServer(self.spec.command, instructions=self.instructions)
        self._register_common_tools()
        self.register_tools()

    @abstractmethod
    def register_tools(self) -> None:
        """Subclasses register their own tools with ``self.mcp.tool()``."""

    def _register_common_tools(self) -> None:
        if not self.spec.purposes:
            return      # nothing model-related to list
        @self.mcp.tool()
        def list_models() -> dict[str, Any]:
            """Show which model each job of this server uses (or "not configured"), and the
            configured model aliases."""
            return self.ctx.models.describe()

    def run(self, *, http: bool = False, host: str = "127.0.0.1",
            port: int | None = None) -> None:
        if http:
            self.mcp.run("streamable-http", host=host, port=port or self.default_port)
        else:
            self.mcp.run("stdio")

    @classmethod
    def build_parser(cls) -> argparse.ArgumentParser:
        p = argparse.ArgumentParser(prog=cls.spec.command, description=cls.instructions)
        p.add_argument("--http", action="store_true",
                       help="serve Streamable HTTP instead of stdio")
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=cls.default_port)
        p.add_argument("--config", help="path to config.toml (replaces the shared file and the "
                       "server file)")
        p.add_argument("--project-config", help="path to a project layer: it can choose models "
                       "and the output folder, never providers, endpoints or keys")
        return p

    @classmethod
    def main(cls, argv: list[str] | None = None) -> None:
        args = cls.build_parser().parse_args(argv)
        # stdout belongs to the stdio transport: log to stderr only.
        logging.basicConfig(stream=sys.stderr, level=logging.INFO)
        try:
            ctx = AppContext.create(cls.spec, args.config, args.project_config)
        except ConfigError as exc:
            # Stdout stays empty (it is the stdio transport); say everything on stderr.
            print(f"{cls.spec.command}: cannot start, the configuration is invalid:",
                  file=sys.stderr)
            for problem in exc.problems:
                print(f"  - {problem}", file=sys.stderr)
            raise SystemExit(2) from None
        # Which files are in effect, so "why is my setting ignored" can be answered. Paths only.
        for layer, path in ctx.settings.sources:
            log.info("%s: loaded %s config %s", cls.spec.command, layer, path)
        if not ctx.settings.sources:
            log.info("%s: no config file found, using defaults", cls.spec.command)
        # Per-field environment variables of the earlier layout no longer do anything.
        old_env = legacy_environment(os.environ)
        if old_env:
            log.warning("%s: ignoring %s: settings come from config files only, and the only "
                        "environment variable read is MYMCPS_CONFIG. See \"Migrating\" in the "
                        "README.", cls.spec.command, ", ".join(old_env))
        # A model that is clearly the wrong kind is worth a warning; the server still starts.
        for warning in ctx.models.check_purposes():
            log.warning("%s: %s", cls.spec.command, warning)
        cls(ctx).run(http=args.http, host=args.host, port=args.port)

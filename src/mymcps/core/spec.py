"""What a server declares about itself: its name and the purposes it needs a model for.

The core knows no server by name. Each server states its own :class:`ServerSpec`, and the core
works from that (ADR 0004).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .abilities import Need

SERVER_NAME_RULE = re.compile(r"^[a-z][a-z0-9-]*$")
PURPOSE_NAME_RULE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class Purpose:
    """A job a server needs a model for, configured as ``<name>_model`` in its section."""

    name: str
    summary: str
    need: Need | None = None    # what its model must be able to do (warned about, not enforced)

    def __post_init__(self) -> None:
        if not PURPOSE_NAME_RULE.match(self.name):
            raise ValueError(
                f"Invalid purpose name {self.name!r}: use lowercase letters, digits and "
                "underscores, starting with a letter.")

    @property
    def field(self) -> str:
        return f"{self.name}_model"


@dataclass(frozen=True)
class ServerSpec:
    """A server's identity: one short name used everywhere in configuration."""

    name: str
    purposes: tuple[Purpose, ...] = ()

    def __post_init__(self) -> None:
        if not SERVER_NAME_RULE.match(self.name):
            raise ValueError(
                f"Invalid server name {self.name!r}: use lowercase letters, digits and "
                "hyphens, starting with a letter.")
        names = [p.name for p in self.purposes]
        if len(set(names)) != len(names):
            raise ValueError(f"Server {self.name!r} declares a purpose twice: {names}")

    @property
    def command(self) -> str:
        """The console command that starts this server."""
        return f"mymcps-{self.name}"

    def purpose(self, name: str) -> Purpose:
        for p in self.purposes:
            if p.name == name:
                return p
        declared = ", ".join(p.name for p in self.purposes) or "none"
        raise KeyError(f"Server {self.name!r} has no purpose {name!r} (declared: {declared})")

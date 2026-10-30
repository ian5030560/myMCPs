"""``${NAME}`` expansion for the string values of the user's config files.

Built-in variables win over environment variables of the same name. ``$$`` is a literal ``$``.
Expansion is a single pass: what a variable expands to is never scanned again, so a value can
neither trigger a second expansion nor loop. A leading ``~`` (alone or before a slash) is the
home directory.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

BUILTIN_VARIABLES = ("CONFIG_DIR", "CWD", "TEMP", "SERVER")

_TOKEN = re.compile(r"\$\$|\$\{([^}]*)\}")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


@dataclass(frozen=True)
class Expanded:
    text: str
    undefined: tuple[str, ...] = ()    # variables with no value; their place is left empty
    malformed: tuple[str, ...] = ()    # `${...}` whose name is not a valid variable name


class VariableExpander:
    def __init__(self, builtins: Mapping[str, str], environ: Mapping[str, str]):
        self._builtins = builtins
        self._environ = environ

    def expand(self, text: str, *, tilde: bool = True, environment: bool = True) -> Expanded:
        prefix = ""
        if tilde and (text == "~" or text.startswith(("~/", "~\\"))):
            prefix, text = str(Path.home()), text[1:]
        undefined: list[str] = []
        malformed: list[str] = []

        def replace(match: re.Match) -> str:
            name = match.group(1)
            if name is None:                      # `$$`
                return "$"
            if not _NAME.match(name):
                malformed.append(name)
                return ""
            value = self._builtins.get(name)
            if value is None and environment:
                value = self._environ.get(name)
            if value is None:
                undefined.append(name)
                return ""
            return value

        return Expanded(prefix + _TOKEN.sub(replace, text), tuple(undefined), tuple(malformed))

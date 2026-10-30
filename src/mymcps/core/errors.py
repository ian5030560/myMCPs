"""Exception hierarchy. Everything derives from ``ToolError`` so the agent sees the message."""

from __future__ import annotations

from mcp.server.mcpserver.exceptions import ToolError


class ConfigError(Exception):
    """The configuration is invalid, so the server cannot start.

    Not a tool error: it happens before any tool runs. ``problems`` holds every problem found,
    each naming the file, section and field, and never a value from the file.
    """

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        super().__init__(chr(10).join(self.problems))


class MediaToolError(ToolError):
    """Base class for all errors raised by mymcps tools."""


class InputError(MediaToolError):
    """Problem with a user-supplied file path or URL."""


class InputNotFoundError(InputError):
    pass


class AccessDeniedError(InputError):
    pass


class DownloadError(InputError):
    pass


class ModelError(MediaToolError):
    """Problem reported by a model provider (translated from LiteLLM)."""


class AuthError(ModelError):
    pass


class ModelNotFoundError(ModelError):
    pass


class RateLimitError(ModelError):
    pass


class ProviderError(ModelError):
    pass


class PurposeNotConfiguredError(MediaToolError):
    """A tool needs a model for a purpose the user has not configured."""

    def __init__(self, server: str, field: str, summary: str):
        super().__init__(
            f"No model is configured for {summary}. Set `{field}` in the "
            f"[{server}] section of your config file, or pass `model` in the call.")


class UnsupportedCapabilityError(MediaToolError):
    """The selected model cannot do what the tool needs."""


class FFmpegError(MediaToolError):
    pass


class MissingExtraError(MediaToolError):
    """An optional dependency group is not installed."""

    def __init__(self, extra: str, package: str):
        super().__init__(
            f"'{package}' is not installed. Run: pip install \"mymcps[{extra}]\""
        )

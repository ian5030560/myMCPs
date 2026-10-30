# 08: Servers that need no model

**What to build:** A server that declares no purposes (for example a future file-conversion server) starts and works without touching anything model-related: it does not read providers or model aliases, does not load LiteLLM and does not offer `list_models`. A broken provider setting can therefore never stop it.

**Blocked by:** 05

**Status:** ready-for-agent

- [x] A test-only server that declares no purposes offers no `list_models` tool.
- [x] Starting it does not import LiteLLM.
- [x] It starts even when providers or model aliases are broken: an unknown field, an undefined variable, or a link to an undefined provider.
- [x] It still validates the top-level settings and its own section.

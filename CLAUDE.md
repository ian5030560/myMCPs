# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

One Python package, `mymcps`, that ships several independent MCP servers (today `image`, `video`, `audio`, started with `mymcps-image` and so on; only `image` has real tools so far, the other two are shells exposing `list_models`). All model calls go through LiteLLM. MCP SDK is `mcp` 2.x (`MCPServer` from `mcp.server.mcpserver`, snake_case result fields such as `is_error`).

**Configuration** follows `.scratch/config-file/spec.md` (implemented; tickets in `.scratch/config-file/issues/`): servers `image`/`video`/`audio` started with `mymcps-<name>`; one `<purpose>_model` per job and no built-in default models; providers (connection details, with a vendor) and model aliases; a single `api_key` field and `${NAME}` variables; strict validation scoped to the running server; layered files (shared, server file, `--project-config` layer); model abilities derived from LiteLLM's table, never declared; servers with no purposes read no model settings. The only environment variable is `MYMCPS_CONFIG`. Names from the earlier layout are rejected with a pointer to the README's "Migrating" section (`LEGACY_*` in `core/config.py`). Read the spec and `docs/adr/` before changing config or core behaviour.

## Commands

Python 3.10 is the baseline (pip + venv, no uv). Always install through the constraints file:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -c requirements.txt -e ".[all,dev]"
```

```bash
ruff check .                                   # lint (line length 100)
pytest                                         # all tests (mocks only, no API keys needed)
pytest tests/image/test_editor.py::test_stability_with_mask_uses_inpaint   # one test
pytest -m "not ffmpeg"                         # skip tests that run the bundled ffmpeg binary
docker compose run --rm --build test           # Linux check, installs with -c requirements.txt
mymcps-image                                   # run a server over stdio
mymcps-image --http --port 8701                # Streamable HTTP (8701/8702/8703 per server)
```

Linux on another Python: `$env:PYTHON_VERSION = "3.10"; docker compose run --rm --build test`. Add `--progress plain` to `docker compose build` to see pip output.

Dependencies: `requirements.txt` pins every runtime dependency (used as a pip constraints file, no hashes). LiteLLM is pinned to an exact version on purpose (ADR 0003). To change a dependency: `pip-compile pyproject.toml --extra all --strip-extras -o requirements.txt --upgrade-package <name>`, review the diff, install into a clean venv and check `site-packages` for unexpected `.pth` files (README "Security").

## Architecture

- **`core/spec.py` `ServerSpec` / `Purpose`**: a server declares its name (lowercase, digits, hyphens) and its purposes; the core knows no server by name. A purpose `gen` is configured as `gen_model` in the `[<server name>]` section. Every server is also listed in the `mymcps.servers` entry-point group in `pyproject.toml`, which the name-uniqueness test iterates, so a new server is covered automatically (reinstall with `pip install -e .` after adding one).
- **`core/server.py` `BaseMediaServer`**: each server subclasses it, sets `spec`, `default_port`, and registers tools in `register_tools()`. The command is `mymcps-<name>`. The base registers `list_models` and parses `--http/--host/--port/--config`.
- **`core/context.py` `AppContext`**: the dependency-injection point. Holds settings, `LLMClient`, `ModelRegistry`, `InputResolver`, `OutputManager`; `ffmpeg` is a lazy property so servers that never use it need no `imageio-ffmpeg`. Tests build it directly with fakes.
- **`core/llm.py` `LLMClient`** is the only module that imports `litellm`. The import is lazy (servers start and list tools without it) and wrapped in `redirect_stdout(sys.stderr)`, because **stdout is the stdio MCP transport**: nothing may print to stdout. LiteLLM exceptions are translated into the `ToolError` subclasses in `core/errors.py` so the agent sees a readable message.
- **`core/models.py`**: `ModelRegistry.resolve(purpose, model)` picks the model for one of the server's purposes (a `model` argument wins; an unset purpose raises `PurposeNotConfiguredError` naming the field), and `resolve_model(name)` turns an alias from `[models.*]` or a raw `vendor/model` string into a `ResolvedModel`; `call_kwargs()` is what gets passed to LiteLLM. A model's provider is its explicit link, else the provider named after its vendor, else a built-in default; `ResolvedModel.vendor` (the provider's vendor) is what vendor-specific behaviour reads, never a string prefix. `core/vendors.py` holds the known vendors and their standard key variables.
- **`core/inputs.py` / `core/outputs.py`**: tools accept local paths or http(s) URLs (downloaded to temp, cleaned up after use) and save results via `OutputManager.save`; tools return `OutputManager.image_result(paths)`, a `[text, Image, ...]` list that MCPServer turns into text plus image content blocks.
- **image server** (`image/`): `ImageGenerator`, `ImageEditor`, `StabilityEditor` are plain classes built from the context; `server.py` only wires them to tools. Behaviour branches on the vendor:
  - **Masks** use one convention, white = edit (`masks.py` `Mask`), converted per vendor. OpenAI wants transparent = edit; Stability takes it as-is. Gemini has no mask parameter, so the editor shows Gemini the mask and then pastes the result back with `Mask.composite`, leaving pixels outside the mask unchanged.
  - **Stability** gets one image per request and does not implement `n` in LiteLLM, so the code loops.
  - **`stability_edit`** maps operations to `stability/<operation>` model strings and is only registered when a Stability key is available. `style`, `style-transfer`, `replace-background-and-relight` and `creative` upscale are deliberately excluded (LiteLLM routing bugs or async APIs).
- **Tool signatures and annotations**: modules use `from __future__ import annotations`, and MCPServer resolves annotations against the module's globals. Types used in a tool signature must therefore be module-level (see `Operation` in `image/server.py`), not locals.

## Tests

- `tests/conftest.py` provides `FakeLiteLLM` (records calls; set `.response` / `.raises`) and `make_ctx(server=..., sections=..., **settings)` to build an `AppContext` around it (it configures `gen_model` and `edit_model` for the image server unless you pass `sections`), plus `png_bytes()` and `image_response()` helpers imported as `from conftest import ...`.
- Server tests use the in-memory `mcp.Client(server.mcp)`; `test_server_smoke.py` also starts a real stdio subprocess.
- `test_llm.py` checks that importing the servers does not load litellm and that a real litellm import writes nothing to stdout. Keep both true.

## Commit messages

Format: `TYPE: SUBJECT`, then an optional body and an optional footer, each separated by a blank line. Chinese or English; this project writes them in Traditional Chinese. Only commit when the user asks.

- **Types** (capitalised): `Feat` new feature, `Modify` change to the requirements of an existing feature, `Fix` bug fix, `Docs` documentation only, `Style` formatting only, `Refactor` restructuring without changing logic, `Test` adding or refactoring tests, `Chore` build configuration, versions and other routine work, `Revert` undoing a commit (`revert: type(scope): subject (回覆版本：xxxx)`).
- **Subject**: at most 50 characters, imperative and brief, no full stop at the end; capitalise the first letter when it is English.
- **Body** (optional): say what changed and why, at most 72 characters per line.
- **Footer** (optional): issue references such as `Resolves: #123`.

## Agent skills

### Issue tracker

Issues and specs are local markdown files under `.scratch/`, tracked in git. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-label vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`, recorded as the `Status:` line of each issue file. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Manual testing

Checks that mocks cannot prove (real APIs, stdio, platforms) live in checklists under `docs/manual-testing/`, one per server, with stable `#N` item IDs. Read `docs/agents/manual-testing.md` before creating or changing one.

# mymcps

MCP servers for AI agents (Claude Code, Claude Cowork, Codex, OpenClaw, ...):

| Command | What it does | Status |
|---|---|---|
| `mymcps-image` | Generate and edit images (OpenAI, Gemini/Imagen, Stability, ...) | Available |
| `mymcps-video` | Summaries, Q&A, timestamped analysis and frame extraction for videos | Planned (only `list_models` today) |
| `mymcps-audio` | Transcription, Q&A, summaries and translation for audio | Planned (only `list_models` today) |

All model calls go through [LiteLLM](https://docs.litellm.ai/), so any `provider/model` string works.

> **Coming from the earlier layout?** The servers, config sections and several settings were
> renamed or removed. See [Migrating](#migrating-from-the-earlier-layout).

## Image server tools

| Tool | What it does |
|---|---|
| `generate_image` | Text to image with the `gen_model` you configured. `model`, `n`, `size`, `quality`, `output_dir`. |
| `edit_image` | Edit with the `edit_model` you configured;  optional `mask` (inpainting) and `references` (extra images). |
| `stability_edit` | Stability AI operations: `remove_background`, `erase`, `outpaint`, `search_and_replace`, `search_and_recolor`, `upscale_fast`, `upscale_conservative`. Only listed when a key is reachable for `stability/...` models (`STABILITY_API_KEY`, or a key on `[providers.stability]`). |
| `list_models` | The model each job uses (or "not configured") and the configured aliases; never shows keys. |

Images are written to disk in the configured output folder (the system temp folder by default); each
tool returns the file paths plus a small preview the agent can look at. The `output_dir` tool argument
may only name a subfolder inside that folder (for example `logos`); absolute paths and `..` are
rejected. `image`, `mask` and `references` accept any local path or http(s) URL.

**Masks:** one convention for every provider: a black-and-white image the same shape as the input,
**white = change, black = keep**. mymcps converts it for each provider.

| Model | mask | references |
|---|---|---|
| `openai/...` | native | yes |
| `gemini/...` | simulated: Gemini is shown the mask, then the result is pasted back so pixels outside the mask are unchanged | yes |
| `stability/...` | native (`edit_image` inpaints); other operations via `stability_edit` | no (one image at a time) |

Not available through Stability: `style`, `style-transfer`, `replace-background-and-relight`,
`creative` upscale, `sketch` and `structure` (LiteLLM routes or forwards them incorrectly or does not
support Stability's asynchronous API).

The image tools have only been tested against a mocked LiteLLM; real API calls are not verified yet.

## Install

Requires Python 3.10+. Always install with the pinned constraints file `requirements.txt`
(see *Security*):

```bash
pip install -c https://raw.githubusercontent.com/ian5030560/myMCPs/main/requirements.txt "mymcps[all] @ git+https://github.com/ian5030560/myMCPs.git"
```

Replace `[all]` with `[image]`, `[video]` or `[audio]` to install only what one server needs
(`video` and `audio` add the bundled ffmpeg).

`-c` only fixes versions; it never installs a package your platform does not need, so the same file
works on Windows, macOS and Linux.

From a clone:

```bash
pip install -c requirements.txt ".[all]"
```

Development:

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows (use `source .venv/bin/activate` elsewhere)
pip install -c requirements.txt -e ".[all,dev]"
```

## Register with an agent

Each server is registered separately and started with `mymcps-<name>`. Put your keys in the config
file as `api_key = "${OPENAI_API_KEY}"`-style references, or pass the standard variables in `env`.
Use **absolute paths** in registrations: MCP clients start servers from different working
directories (one report says Claude Desktop uses the filesystem root).

Claude Code:

```bash
claude mcp add image -e OPENAI_API_KEY=sk-... -- mymcps-image --config /home/me/.mymcps/config.toml
```

Claude Desktop / Cowork (`claude_desktop_config.json`), here with a project layer:

```json
{
  "mcpServers": {
    "image": {
      "command": "mymcps-image",
      "args": ["--project-config", "/home/me/work/site/.mymcps/image.toml"],
      "env": { "OPENAI_API_KEY": "..." }
    }
  }
}
```

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.image]
command = "mymcps-image"
args = ["--project-config", "/home/me/work/site/.mymcps/image.toml"]
env = { OPENAI_API_KEY = "..." }
```

Remote use: `mymcps-image --http --host 127.0.0.1 --port 8701` (Streamable HTTP). The HTTP server has
**no authentication and no folder restriction**: any client that can reach the port can make it read
any file the process can read and write into its output folder. Keep it on localhost or put it
behind a proxy that authenticates.

## Configuration

See [config.example.toml](config.example.toml). Settings come from files only; `MYMCPS_CONFIG` (the
path to a file) is the one environment variable read.

**Layers.** A server reads up to three files, later ones overriding earlier ones:

1. the shared file `~/.mymcps/config.toml`, for every server;
2. an optional server file `~/.mymcps/image.toml` (or `video.toml`, `audio.toml`), for that server
   only. It may hold top-level settings, providers, models and its own server's section, and nothing
   else, so a mistake in it stops only that server;
3. an optional project layer, only when you name it with `--project-config <file>` in the server's
   registration (use an absolute path; the conventional place is `<project>/.mymcps/<server>.toml`).
   Nothing is discovered automatically, so a repository you merely cloned cannot change your setup.

`--config` or `MYMCPS_CONFIG` names a file that is the whole global layer by itself: no server file
is loaded next to it. A path you name explicitly must exist.

A single value (`output_dir`, `max_download_mb`) is overridden by the later file, a server section is
merged field by field, and providers and model aliases merge by name with the **whole entry**
replaced, never half-mixed. The `output_dir` tool argument is a subfolder of the result. The output
folder is the server section's `output_dir`, else the top-level one, else `<temp>/mymcps/<server>`.

**The project layer cannot change where data is sent.** It may set the top-level `output_dir`, its
server's section, and model aliases that give only `model` and a `provider` link to a provider of
your own files. Providers, endpoints, keys, passthrough parameters and `max_download_mb` there are
errors, and it expands only the built-in variables, never environment variables. So it never holds
a secret and is safe to commit (see [ADR 0002](docs/adr/0002-project-layer-cannot-change-where-data-is-sent.md)).

On startup the server writes to stderr which files it loaded and as which layer (paths only, never
a value), so "why is my setting ignored" can be answered.

**Choose your models.** There are no built-in default models: each server section has one
`<job>_model` field per job, holding a `[models.<alias>]` name or a LiteLLM string such as
`openai/gpt-image-2`:

| Server | Section | Fields |
|---|---|---|
| image | `[image]` | `gen_model` (generate_image), `edit_model` (edit_image) |
| video | `[video]` | `watch_model` |
| audio | `[audio]` | `listen_model`, `transcribe_model` |

A mistake in the config stops the server at startup, and every problem is listed at once, each naming
the file, section and field (never the value). Unknown fields and sections are errors, with a
suggestion when it looks like a typo. A server checks only the top-level settings, the model aliases
and its own section, so a typo in another server's section does not stop it, but a section named
after no server (for example `[imgae]`) does. A config path you name with `--config` or `MYMCPS_CONFIG`
must exist; a missing `~/.mymcps/config.toml` is simply skipped.

A server starts even when a job has no model. The tool that needs it then fails with a message naming
the field to set, and passing `model` in the call always works. `list_models` shows each job's model.

The servers do not restrict which files a tool may read: any local path or URL the agent passes is
accepted. Access control is left to the agent and its MCP client
(see [ADR 0001](docs/adr/0001-servers-do-not-restrict-file-access.md)).

**Providers.** Connection details (endpoint, key, passthrough parameters) live in
`[providers.<name>]`, defined once and shared by several `[models.<alias>]` entries. Every model uses
exactly one provider:

1. the provider its alias links to (`provider = "local"`), else
2. the provider named after its vendor (the part of the model string before the slash), so
   `[providers.stability]` applies to every `stability/...` model, raw strings included, else
3. a built-in default that uses LiteLLM's standard variables (`OPENAI_API_KEY`, `GEMINI_API_KEY`,
   `STABILITY_API_KEY`, ...).

A provider whose name is not a vendor (say `local`) is reached only through an explicit link, so a raw
`openai/...` string still goes to the real OpenAI and your OpenAI key never reaches your local server.
A provider says which vendor's API it speaks with `vendor`; that defaults to its name when it is a
known vendor, otherwise to the vendor of the models linked to it. Behaviour that differs per vendor
(mask handling, Stability's one-image-per-call) follows the provider's vendor, so a self-hosted
OpenAI-compatible server is treated like OpenAI. For local servers LiteLLM's dedicated prefixes
(`hosted_vllm/`, `lm_studio/`, `ollama/`) usually need no link at all.

The key is the single field `api_key`: a literal, or `${LOCAL_API_KEY}` to keep the secret out of the
file. A key whose variable is unset means "no key": the server still starts, `list_models` shows
`key_configured: false`, and an authentication failure names the variable.
Passthrough parameters (`[providers.x.extra]`, `[models.x.extra]`) merge provider first, then model,
and the model wins on the same key. An alias name cannot contain `/`; a link to an undefined
provider, or to a provider of another vendor, stops the server. `list_models` shows each alias with
its provider, vendor and `key_configured` (false only when a key is expected but missing), and never a
key or an endpoint.

**Variables and paths.** Every string value in the config can use `${NAME}`: the built-ins
`${CONFIG_DIR}` (the folder of the file the value is written in), `${CWD}` (the working directory,
which differs per MCP client, so avoid it), `${TEMP}` and `${SERVER}` (the server's name), then any
environment variable. Built-ins win over environment variables of the same name. A leading `~` is the
home directory, `$$` is a literal `$`, and expansion happens once, so a value is never expanded
twice. An undefined variable stops the server (naming file, section and field), except in `api_key`.
Variables are never expanded in tool arguments. A relative path in a config file is relative to that
file, so `output_dir = "results"` means the same whichever client started the server; `--config` and
`MYMCPS_CONFIG` themselves are used as given. On Windows write paths with forward slashes or
single-quoted strings, because `"C:\Users"` is a TOML escape error. Register servers with absolute
paths, since client working directories differ.

**Model abilities are derived, never declared.** The servers read what a model can do (chat, image
output, transcription, vision, audio input) from LiteLLM's model table, plus one rule: Gemini chat
models read video directly. A model the table does not list (self-hosted, brand new) is *unknown*
and simply tried; it is never treated as incapable. At startup each configured purpose is checked,
and a model that is known to be the wrong kind (say a chat model as `gen_model`, or a model without
audio input as `listen_model`) produces a warning on stderr; the server starts anyway, because the
table can be out of date. `list_models` shows each alias's abilities, or `"unknown"`. Checking
needs LiteLLM's table, so a server with a configured model loads LiteLLM at startup.

**Servers that need no model.** A server that declares no model jobs (a future file converter, say)
does not read, expand or validate `[providers]` and `[models]`, does not load LiteLLM and has no
`list_models` tool, so a broken provider setting can never stop it. It still checks the top-level
settings and its own section.

## Migrating from the earlier layout

The project is unreleased, so the old names were removed rather than kept alongside the new ones.
Every one of them now fails loudly: an old name in a config file stops the server with an error that
says what replaced it and points here.

| Earlier | Now |
|---|---|
| commands `image-gen`, `video-watch`, `audio-listen` | `mymcps-image`, `mymcps-video`, `mymcps-audio` |
| sections `[image_gen]`, `[video_watch]`, `[audio_listen]` | `[image]`, `[video]`, `[audio]` |
| `default_model`, `image_model`, `video_model`, `audio_model`, `transcription_model` | one field per job: `gen_model`, `edit_model` (image), `watch_model` (video), `listen_model`, `transcribe_model` (audio). There are no built-in defaults |
| `api_base` and `api_key` on `[models.<alias>]` | move them to `[providers.<name>]` and link the alias with `provider = "<name>"` |
| `api_key_env = "VAR"` | `api_key = "${VAR}"`. An unset variable means "no key" |
| `capabilities = [...]` | removed; abilities are derived from LiteLLM's table (`list_models` shows them) |
| `allowed_dirs` and `MYMCPS_ALLOWED_DIRS` | removed. Servers read any path or URL the agent gives them; the `output_dir` tool argument is a subfolder of the output folder |
| `MYMCPS_OUTPUT_DIR`, `MYMCPS_IMAGE_MODEL`, ... | removed; settings come from files. Only `MYMCPS_CONFIG` is read. Old ones set in `env` are ignored with a warning |
| `[models.stability]` supplying the Stability connection | `[providers.stability]`, which applies to every `stability/...` model |
| one `config.toml` for everything | still works, plus an optional `~/.mymcps/<server>.toml` and a `--project-config` layer |
| relative paths resolved against the working directory | resolved against the config file's folder |

A minimal before and after for the image server. Before:

```toml
[image_gen]
default_model = "mine"
allowed_dirs = ["~/Pictures"]

[models.mine]
model = "openai/qwen"
api_base = "http://localhost:8000/v1"
api_key_env = "LOCAL_API_KEY"
capabilities = ["vision"]
```

After:

```toml
[providers.local]
vendor = "openai"
api_base = "http://localhost:8000/v1"
api_key = "${LOCAL_API_KEY}"

[models.mine]
model = "openai/qwen"
provider = "local"

[image]
gen_model  = "mine"
edit_model = "mine"
```

## Development

```bash
ruff check .
pytest                                    # mocks only, no API keys needed
pytest tests/image/test_editor.py     # one file (or append ::test_name for one test)
pytest -m "not ffmpeg"                    # skip tests that run the bundled ffmpeg binary
```

Linux check in Docker. It installs with `-c requirements.txt` and runs the tests against the
installed package:

```bash
docker compose run --rm --build test
```

Pick the Python version with `PYTHON_VERSION` (default 3.12):

```powershell
$env:PYTHON_VERSION = "3.10"; docker compose run --rm --build test
```

Add `--progress plain` to `docker compose build` to see pip's live output. `docker compose run --rm
freeze` lists the exact versions installed on Linux.

Verified: the full suite on Windows + Python 3.10, and in Docker on Linux with Python 3.10 and 3.12
(333 passed, 1 skipped each). macOS has not been checked.

Project documents:

- [GLOSSARY.md](GLOSSARY.md): the project's vocabulary.
- [docs/adr/](docs/adr/): architecture decisions and why they were made.
- [docs/manual-testing/](docs/manual-testing/): checks against real providers that the mock tests cannot make.
- `.scratch/`: specs and issues (local markdown tracker, see [docs/agents/](docs/agents/)).

## Security

LiteLLM versions 1.82.7 and 1.82.8 were compromised on PyPI on 2026-03-24 by publishing new,
malicious releases. `requirements.txt` pins the exact version of every runtime dependency, direct and
transitive, so a newly published release is never picked up until the pins are deliberately updated
(see [ADR 0003](docs/adr/0003-litellm-for-all-model-calls-pinned-exactly.md)).

Limits of this approach:

- pip does not support hashes in a constraints file, so files are not hash-verified.
- `requirements.txt` is generated on Windows. A package needed only on macOS/Linux would not appear in
  it and would resolve to its latest version there. On Linux this currently affects no runtime
  dependency (checked against what Linux actually installs); macOS has not been checked.

Updating dependencies:

1. `pip-compile pyproject.toml --extra all --strip-extras -o requirements.txt --upgrade-package <name>`
   (or `--upgrade` for everything).
2. Review the diff of `requirements.txt`. For a LiteLLM bump, check its release notes and security
   advisories first.
3. Install into a clean venv with `pip install -c requirements.txt ".[all]"`, confirm no unexpected
   `.pth` files appear in `site-packages`, and run the tests.

## License

MIT

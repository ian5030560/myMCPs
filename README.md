# mymcps

MCP servers for AI agents (Claude Code, Claude Cowork, Codex, OpenClaw, ...):

| Command | What it does |
|---|---|
| `image-gen` | Generate and edit images (OpenAI, Gemini/Imagen, Stability, ...) |
| `video-watch` | Summaries, Q&A, timestamped analysis and frame extraction for videos |
| `audio-listen` | Transcription, Q&A, summaries and translation for audio |

All model calls go through [LiteLLM](https://docs.litellm.ai/), so any `provider/model` string works.

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

Each server is registered separately. Set the API keys of the providers you use in `env`.

Claude Code:

```bash
claude mcp add image-gen -e OPENAI_API_KEY=sk-... -- image-gen
```

Claude Desktop / Cowork (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "video-watch": { "command": "video-watch", "env": { "GEMINI_API_KEY": "..." } }
  }
}
```

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.audio-listen]
command = "audio-listen"
env = { GEMINI_API_KEY = "..." }
```

Remote use: `image-gen --http --host 127.0.0.1 --port 8701` (Streamable HTTP).

## Configuration

Optional. See [config.example.toml](config.example.toml). Lookup order: `--config`, `MYMCPS_CONFIG`,
`~/.mymcps/config.toml`. Priority: tool argument > environment variable > TOML > built-in default.

Environment variables: `MYMCPS_OUTPUT_DIR`, `MYMCPS_ALLOWED_DIRS` (separated by `os.pathsep`),
`MYMCPS_IMAGE_MODEL`, `MYMCPS_VIDEO_MODEL`, `MYMCPS_AUDIO_MODEL`, `MYMCPS_TRANSCRIPTION_MODEL`.

API keys use LiteLLM's standard variables (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `STABILITY_API_KEY`, ...)
or the `api_key_env` of a `[models.<alias>]` entry.

## Testing

```bash
pip install -c requirements.txt -e ".[all,dev]"
pytest
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

Verified so far: Windows + Python 3.10, Linux + Python 3.10 and 3.12.

## Security

LiteLLM versions 1.82.7 and 1.82.8 were compromised on PyPI on 2026-03-24 by publishing new,
malicious releases. `requirements.txt` pins the exact version of every runtime dependency, direct and
transitive, so a newly published release is never picked up until the pins are deliberately updated.

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

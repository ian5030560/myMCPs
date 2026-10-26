Status: ready-for-agent

# Config redesign: providers, purposes, layered files, extensible servers

## Problem Statement

The config file works for the simplest cases but breaks down as soon as a user does anything real, and it will not scale to the additional MCP servers planned for this project:

- **The core hard-codes three servers.** Their names, sections, default models and environment variables are written into the shared core, and each server has two names (a section name and a command name). Adding a server means editing the core.
- **Connection settings are tied to model aliases.** A self-hosted endpoint serving several models must be repeated in every model entry. An agent that passes a raw model string never receives any connection setting. Stability support depends on a hidden convention: an alias that happens to be named `stability`.
- **The code uses one word for two things.** What the code calls a model's "provider" is really its vendor (the API family it speaks), which collides with the connection settings users need to name.
- **Built-in default models hide what is actually being called**, and every server has a single generic "default" model even when it needs different models for different jobs.
- **API keys can only come from an environment variable by naming it in a second field**, and a missing variable silently becomes "no key". An agent cannot tell, before calling, whether a model is usable.
- **Typos are silently ignored.** A misspelled field is dropped and the setting never takes effect.
- **Precedence is surprising**, and per-field environment variables add a whole extra layer of rules.
- **Relative paths depend on the working directory of whatever process started the server**, and that directory differs per MCP client (one user report says Claude Desktop starts servers from the filesystem root; OpenClaw does not document its default; Hermes depends on the session).
- **There is one config file for everything.** A user cannot tailor one server without touching the others, and one typo stops every server.
- **Capability declarations and a folder allow-list add configuration surface** the servers barely need, and the capability lookup treats models LiteLLM does not know as incapable.

## Solution

- **Servers are named `image`, `video` and `audio`**, one name used everywhere in configuration; their commands are `mymcps-image`, `mymcps-video` and `mymcps-audio`. Each server declares its own section fields and the purposes it needs a model for; the shared core contains no server names, so a new server needs no core change.
- **Purposes:** each job a server needs a model for is a field `<purpose>_model` in that server's section: `image` has `gen_model` and `edit_model`, `video` has `watch_model`, `audio` has `listen_model` and `transcribe_model`. There are no built-in default models; the user configures each one.
- **Providers** hold connection details (vendor, endpoint, key) once. **Model aliases** say which model to call and, optionally, which provider carries it. Every model resolves to exactly one provider: the one it links to, else the one named after its vendor, else a built-in default for that vendor.
- **A single `api_key` field** takes either a literal key or `${LOCAL_API_KEY}`. The same `${...}` syntax works in every string value of the user's own config files, plus built-in variables for paths.
- **Strict validation, scoped per server.** Unknown fields and unknown variables (except in a key) fail at startup, all errors at once, naming file, section and field. Each server validates only what it uses, so another server's mistake does not stop it.
- **Files, not environment variables:** a shared `~/.mymcps/config.toml`, an optional server file per server (`~/.mymcps/image.toml` and so on), and an optional project layer named at registration. The only environment variable is `MYMCPS_CONFIG`.
- **Predictable precedence and paths:** tool argument, then project layer, then server file, then shared file; relative paths are relative to the file they are written in.
- **No folder allow-list and no capability declarations.** File access is left to the agent and its client; what a model can do is derived from LiteLLM's model table and tried at call time.
- **`list_models`** shows each purpose's model (or "not configured"), the available aliases, their provider and vendor, what they are known to do, and whether they have a key.

Example shared file (`~/.mymcps/config.toml`):

```toml
output_dir = "~/Pictures/mymcps/${SERVER}"

[providers.local]                     # not a vendor name: models must link to it
vendor   = "openai"                   # speaks the OpenAI-compatible API
api_base = "http://localhost:8000/v1"
api_key  = "${LOCAL_API_KEY}"

[providers.stability]                 # named after a vendor: applies to every stability/... model
api_base = "https://ai-proxy.corp/stability"
api_key  = "${CORP_STAB_KEY}"

[models.qwen-vl]
model = "openai/qwen2.5-vl"
provider = "local"

[models.gpt-image]
model = "openai/gpt-image-2"

[image]
gen_model  = "gpt-image"
edit_model = "gpt-image"

[video]
watch_model = "qwen-vl"

[audio]
listen_model     = "gemini/gemini-2.5-flash"
transcribe_model = "openai/whisper-1"
```

## User Stories

**Servers and purposes**
1. As a user, I want each server to have one short name (`image`, `video`, `audio`) used in its section, its server file, its project file and `${SERVER}`, so that I never translate between two spellings.
2. As a user, I want the installed commands to be `mymcps-image`, `mymcps-video` and `mymcps-audio`, so that they cannot clash with other programs on my PATH.
3. As a maintainer adding a new MCP server to this project, I want the server to declare its own section fields and purposes, so that I never have to change the shared core.
4. As a user, I want every model a server needs to be a clearly named `<purpose>_model` field in that server's section, so that I know exactly which model each tool uses.
5. As a user of `image`, I want separate `gen_model` and `edit_model`, so that I can generate with one model and edit with another.
6. As a user of `audio`, I want separate `listen_model` and `transcribe_model`, so that understanding and transcription can use different models.
7. As a user, I want no model chosen for me silently, so that I always know what is called and what it costs.
8. As a user who has not configured a purpose yet, I want the server to start anyway, so that `list_models` still tells me what is missing.
9. As an agent, I want a call that needs an unconfigured purpose to fail with a message naming the field to set, so that the user can fix it in one step.
10. As an agent, I want to pass `model` on a call to use a model even when the purpose is unconfigured, so that I am not blocked by missing configuration.
11. As a user, I want a `*_model` field a server does not declare to be a startup error, so that a misspelled purpose is caught.
12. As a user, I want a purpose's model that is clearly the wrong kind (for example an image model as `watch_model`) reported as a warning at startup, so that I notice the mistake while the server still starts if LiteLLM's table is out of date.
13. As a user, I want models LiteLLM does not know to be treated as "unknown" and simply tried, so that self-hosted and brand-new models are never rejected.
14. As a user of a future server that needs no AI model, I want it not to read or validate providers and model aliases at all, so that a broken provider setting never stops it.
15. As a user of such a server, I want it not to load LiteLLM and not to offer `list_models`, so that it starts fast and shows only relevant tools.

**Providers and models**
16. As a user with a self-hosted endpoint, I want to define its URL and key once and link several models to it, so that I do not repeat connection details.
17. As a user behind a corporate proxy for Stability, I want one provider named `stability` to apply to every Stability model, so that all Stability operations go through the proxy without extra wiring.
18. As a user, I want a provider named after a vendor to apply to raw model strings an agent passes directly, so that agents are not forced to use aliases to benefit from my config.
19. As a user with a self-hosted OpenAI-compatible endpoint, I want models to link to it explicitly, so that raw `openai/...` strings still reach the real OpenAI and my OpenAI key is never sent to my local server.
20. As a user, I want an explicit link to take priority over the provider named after the vendor, so that I can route a specific alias elsewhere.
21. As a user, I want a model with no configured provider to use LiteLLM's standard environment variables and endpoints, so that cloud models need no provider entry.
22. As a user, I want a provider to state which vendor's API it speaks, so that a self-hosted OpenAI-compatible server is treated like OpenAI for behaviour such as image editing.
23. As a user, I want a model linked to a provider of a different vendor to be a startup error, so that a mistaken link is caught immediately.
24. As a user running a self-hosted server, I want the docs to recommend LiteLLM's dedicated prefixes (for example `hosted_vllm/`, `lm_studio/`, `ollama/`), so that I usually need no explicit link.
25. As a user, I want passthrough parameters on both providers and models, with the model's value winning on a clash, so that I can set a provider-wide timeout and override it for one slow model.
26. As a user, I want alias names that contain `/` to be rejected, so that an alias can never be confused with a raw model string.
27. As a user, I want to use one alias in several servers' purposes, so that I define a model once.

**Keys**
28. As a user, I want to write my API key directly in a config file without being warned, so that I am not nagged about a choice I made deliberately.
29. As a user, I want to write `${LOCAL_API_KEY}` as the key value, so that the secret stays out of the file.
30. As a user, I want a single key field, so that there is no ambiguity about which of two fields wins.
31. As a user, I want a key that references an unset environment variable to mean "no key" rather than stop the server, so that a provider I am not using cannot break startup.
32. As an agent, I want `list_models` to tell me whether each model has a key, so that I avoid calling a model that will certainly fail.
33. As an agent, I want the failure message for a missing key to name the unset environment variable, so that the user knows exactly what to fix.
34. As a user, I want `list_models` never to reveal keys or endpoint URLs, so that an agent cannot leak them.

**Variables and paths**
35. As a user, I want `~`, `${CONFIG_DIR}`, `${CWD}`, `${TEMP}` and `${SERVER}` in config values, so that one config works across machines and servers.
36. As a user, I want `${SERVER}` in the shared `output_dir`, so that each server gets its own subfolder.
37. As a user, I want any environment variable usable as `${NAME}` in my own config files, so that I can parameterise endpoints, keys and paths.
38. As a user, I want `$$` to mean a literal `$`, so that values containing a dollar sign stay possible.
39. As a user, I want `${...}` expanded only once, so that a value can never trigger a second expansion or a loop.
40. As a user, I want an undefined variable outside a key to stop startup with a clear message, so that a broken path does not silently point somewhere unexpected.
41. As a user, I want relative paths in a config file to be relative to that file, so that behaviour does not depend on which client launched the server.
42. As a user on Windows, I want the docs to tell me to use forward slashes or single-quoted strings, so that `"C:\Users"` parse errors do not surprise me.
43. As an agent, I want a relative `output_dir` tool argument to resolve under the configured output folder, so that I can organise results without knowing the server's working directory.
44. As a user, I want an absolute or escaping (`..`) `output_dir` tool argument to be rejected, so that the server only ever writes inside its output folder and moving files elsewhere is left to the agent's own, permission-checked file tools.
45. As a user, I want variables never to be expanded inside tool arguments, so that an agent cannot name a folder `${OPENAI_API_KEY}` and read my key back from the returned path.

**Files and layers**
46. As a user, I want all settings to live in files, with `MYMCPS_CONFIG` the only environment variable, so that there is one place to look.
47. As a user, I want an optional `~/.mymcps/image.toml` (and `video.toml`, `audio.toml`) layered over the shared file for that server only, so that I can tailor one server without editing the others.
48. As a user, I want a mistake in one server's section or server file to stop only that server, so that the other servers keep working.
49. As a user who names `--config` or `MYMCPS_CONFIG` explicitly, I want exactly that file loaded and no server file, so that an explicit choice is never silently extended.
50. As a user, I want a config path I named explicitly that does not exist to stop startup, so that I never believe a file is in effect when it is not.
51. As a user, I want a misspelled field to stop startup with the file, section and field named, and every error reported in one go, so that a typo never silently disables a setting and I do not restart once per typo.
52. As a user working on several projects, I want a project layer with its own purpose models and output folder, so that results land in the right project.
53. As a user, I want the project layer to be supplied explicitly in the registration (absolute path recommended), so that a repository I merely cloned can never change my configuration.
54. As a user, I want the docs to suggest a conventional location `<project>/.mymcps/<server>.toml`, so that projects look alike.
55. As a user, I want the project layer to be unable to define providers, endpoints, keys or model passthrough parameters, and to expand only built-in variables, so that a project can choose which model is used but never where my data is sent or which secrets appear in paths.
56. As a team, I want project layer files to be safe to commit, so that we can share them in the repository.
57. As a user, I want models and providers merged by name with the whole entry replaced, so that an entry is never a half-and-half mix of two files.
58. As a user debugging "why is my setting ignored", I want the server to log on stderr which files it loaded and from where, without any values, so that I can see the layering.

**Other**
59. As a maintainer, I want the Stability tool to appear only when a Stability key is reachable, so that agents never see a tool that cannot work.
60. As a user running `--http`, I want the docs to state that the server has no authentication and no folder restriction, so that I keep it on localhost or behind an authenticating proxy.
61. As an existing tester of this unreleased project, I want old names (`[image_gen]`, `MYMCPS_IMAGE_MODEL`, `api_key_env`, `capabilities`, `allowed_dirs`, the `image-gen` command) to fail loudly with the README explaining the new form, so that nothing silently stops working.

## Implementation Decisions

**Server declaration and naming**
- Each server declares: its name (lowercase letters, digits and hyphens, starting with a letter; unique across the project, enforced by a test), its section's own fields, and its purposes. A server with no purposes is a non-model server.
- The name is used for the config section, the server file, the project file convention, `${SERVER}` and the Python subpackage. The command is `mymcps-<name>`. Current servers: `image`, `video`, `audio`.
- The shared core holds no server names, default models or per-server special cases; the existing hard-coded server list, default-model table, per-server settings fields and the special handling for the transcription model are removed.
- No compatibility with old names; they are reported as unknown sections or fields.

**Purposes**
- A purpose is declared by a server with a name and a purpose check. In the config it appears only as `<purpose>_model` inside that server's section (shared file, server file or project layer), never at the top level. Purpose names need only be unique within their server.
- Current purposes: `image`: `gen` (generate_image), `edit` (edit_image); `video`: `watch` (summaries, Q&A, timestamped analysis); `audio`: `listen` (Q&A, summaries, translation), `transcribe` (speech to text).
- No built-in default models. An unconfigured purpose does not stop startup; a tool that needs it fails with a message naming the field and section, unless the call passes `model`.
- A purpose check runs at startup for each configured purpose and only warns (stderr): `gen` and `edit` must produce images; `watch` must be a chat model that reads video or images; `listen` must be a chat model that accepts audio; `transcribe` must transcribe. Models absent from LiteLLM's table are never warned about.
- What a model can do is derived internally, never declared: from LiteLLM's model table (mode, vision and audio-input flags) plus one vendor rule (vendor `gemini` chat models read video directly). A model absent from the table is "unknown" on every count; LiteLLM's helpers answer "no" for unmapped models, so table membership is checked first. At call time unknown abilities are simply tried.

**Non-model servers**
- Do not read, expand or validate providers or model aliases, do not load LiteLLM, and do not offer `list_models`. They read the top-level settings and their own section.

**Validation scope**
- Every server validates the top-level settings and its own section. Servers with purposes also validate providers and model aliases. Other servers' sections are checked only for being known server names; their contents are not read. A server file may contain only top-level settings, providers, models and its own server's section.
- Unknown fields fail startup; passthrough parameter contents are not validated. All errors are collected and reported together, each naming file, section and field. Variable expansion errors follow the same scope.
- A path named explicitly (`--config`, `MYMCPS_CONFIG`, `--project-config`) that does not exist fails startup; default-location files that do not exist are skipped.

**Providers and model aliases**
- A provider has a name, a vendor, an optional endpoint, an optional key and optional passthrough parameters. Its vendor defaults to its name when the name is a known vendor; otherwise it is stated explicitly or taken from the models that link to it (disagreement among them is a startup error).
- A model alias has a model string, an optional provider link and optional passthrough parameters. No capabilities field. Alias names may not contain `/`.
- Resolution: explicit link, else the provider named after the model's vendor, else a built-in default provider for that vendor with no overrides. Every resolved model therefore has a provider. A provider whose name is not a vendor is reachable only through an explicit link. A link to an undefined provider, or to a provider that states a different vendor, is a startup error.
- The resolved model carries its provider including the vendor; behaviour that differs per vendor (image editing paths, Stability looping, file upload routing, which key variable an error message names) reads the provider's vendor. This replaces what the code currently calls the model's provider.
- Parameters sent to LiteLLM: provider passthrough parameters, then the model's (model wins), plus the provider's endpoint and key.
- The special alias named `stability` used by the Stability editor is removed; the editor resolves its fixed `stability/...` model strings like any other model.

**Keys and variables**
- One key field, literal or `${NAME}`; the separate key-environment-variable field is removed. Literal keys produce no warning.
- `${NAME}` expands in every string value of the shared file and server files, including nested passthrough tables: built-in variables first, then environment variables. `$$` is a literal `$`. Single pass; expanded text is never expanded again.
- Built-ins: `CONFIG_DIR` (folder of the file the value is written in), `CWD` (documented as client-dependent and unreliable), `TEMP`, `SERVER`. A leading `~` is the home directory.
- Undefined variable: startup error naming file, section and field, except in a key field, where it means "no key" and the variable's name is remembered for later error messages.
- The project layer expands only built-in variables; any other `${NAME}` there is an error. Variables are never expanded in tool arguments. `MYMCPS_CONFIG` is used as given (relative to the working directory).

**Files, layers and precedence**
- Global layer = shared file plus optional server file: `~/.mymcps/config.toml` and `~/.mymcps/<server>.toml`, both optional. When `--config` or `MYMCPS_CONFIG` names a file, that file alone is the global layer and no server file is loaded.
- Project layer: only via `--project-config`; no automatic discovery. Conventional location `<project>/.mymcps/<server>.toml` (documentation only). It may not contain providers, endpoint or key fields, or model passthrough parameters; its aliases may only set the model string and a link to a global provider. It never holds secrets, so it can be committed.
- Per-field environment variable overrides are removed; `MYMCPS_CONFIG` is the only environment variable the config reads.
- Merge order: shared file, then server file, then project layer. Single values are overridden by the later file; models and providers merge by name with whole-entry replacement. Tool arguments override the merged result.
- Output folder: within the merged config, the server section's `output_dir`, else the top-level `output_dir`, else `<temp>/mymcps/<server>`. A tool argument `output_dir` must be relative and selects a subfolder of that folder; absolute paths and `..` escapes are rejected.
- Relative paths in a file are relative to that file's folder.
- On startup the server logs to stderr each file it loaded, its layer and its path. Never values.

**Removed**
- The folder allow-list (config field, its environment variable, the read and write path checks). Reading any local path or URL the agent provides is left to the agent and its client.
- Capability declarations, built-in default models, per-field environment variables.

**`list_models`** (servers with purposes only)
- For each of the server's purposes: the configured alias or model string, or "not configured".
- For each configured model alias: its model string, provider name, vendor, derived abilities (or "unknown"), and `key_configured`. Never keys or endpoints.
- `key_configured` is false only when a key is expected but unavailable (the configured key did not resolve, or the vendor has a known standard key variable that is unset and no key is configured); otherwise true, including self-hosted endpoints that need no key and cases that cannot be determined.

**Stability tool availability**
- Registered only when a key is reachable for `stability/...` models: a key on the provider that resolves for them, or the standard environment variable.

**Documentation**
- Example config and README updated: new server names and commands, purposes with suggested models to copy (there are no defaults), the provider rules, layers, migration notes for every removed or renamed item, Windows path advice, the advice to use absolute paths in client registrations because client working directories differ, LiteLLM's dedicated prefixes for self-hosted servers, and a warning that `--http` has no authentication and no folder restriction.

## Testing Decisions

- **A good test** feeds config file texts and an environment dictionary into the system and asserts only external behaviour: effective settings, the parameters that would be sent to LiteLLM for a given purpose or model name, the resolved provider and vendor, `list_models` output, startup warnings, and startup errors (type, and that every message names file, section and field). No test inspects internal structures.
- **One seam:** config file texts (shared, optional server file, optional project layer) plus an environment dictionary plus a server declaration, through to the loaded settings and the model registry's resolution and description. A small helper builds that chain with the fake LiteLLM already used in the suite. It replaces the two existing separate config-loading and model-registry test files.
- **Test-only server declarations** (one with purposes, one without) exercise extensibility and the validation scope without depending on the real servers.
- The output manager's folder selection stays its own existing seam, rewritten for the tool-argument rule (relative only, escape rejected, no variable expansion), with the allow-list tests removed.
- The Stability editor and image server tests are updated for the new names, purposes (`gen_model`, `edit_model`), provider resolution (no `stability` alias), vendor-based behaviour and the availability rule, using the existing fake LiteLLM and in-memory MCP client.
- **Prior art:** the existing config-loading, model-registry, output-manager, input-resolver, Stability editor and image server tests; the fake LiteLLM and context-building fixtures. The fake LiteLLM gains a model table so "known", "unknown" and "known but lacking" can all be exercised.
- Cases at the seam: server name rules and uniqueness; undeclared `*_model` field rejected; unconfigured purpose starts and errors only at use; `model` argument overrides; purpose check warns only for known mismatches; non-model server ignores broken providers and loads no LiteLLM; another server's broken section does not stop this server; unknown section name rejected; server file containing another server's section rejected; provider by vendor name; explicit link beats vendor name; raw model string gets the vendor-named provider; non-vendor provider never applied without a link; undefined link; vendor mismatch; built-in default provider; extra merge with model winning; alias with `/` rejected; literal key; `${VAR}` key set and unset; undefined variable elsewhere fails; `$$`; single-pass expansion; every built-in variable; unknown field in each file kind; all errors reported together; explicit missing path fails, default missing path skipped; server file layered over shared file; explicit `--config` disables the server file; project layer forbidden content and variables; whole-entry replacement; full precedence order; relative path base per file kind; `key_configured` cases; `list_models` never contains a key or endpoint; startup log lists files without values; old names rejected.

## Out of Scope

- **Purpose sections** (configuring each purpose once in its own section, shared by every server that uses it); to be evaluated later, after more servers exist.
- Packaging changes for future servers beyond the rename, and default port allocation for `--http`.
- Automatic discovery of a project layer, and trust lists of project folders.
- Checking that an input really is an image, video or audio file before uploading it (a separate item).
- Authentication for `--http`.
- Secret managers, OS keychains or encrypted key storage; hot reload; a setup wizard.
- YAML or any other config format (TOML only).
- A tool argument that lets the agent force the video route (direct video vs extracted frames); this belongs to the video server design.
- Changes to tool behaviour beyond reading purposes and the vendor from the provider.
- Cost limits, usage logging, per-call model allow-lists.
- Verifying real provider behaviour; tests use the fake LiteLLM only.

## Further Notes

- The working-directory findings rest on: one user report for Claude Desktop on macOS (servers start at `/`, closed as not planned, no maintainer reply; nothing found for Windows), OpenClaw's official docs (a `cwd` option exists, the default is not stated), and Hermes' docs and issues (`cwd` option; default is the pinned session directory else the Hermes process directory; an open report says ACP-mode servers are shared across sessions).
- The repository's ignore rule `config.toml` matches that name in every folder; anchoring it to the repository root would be more precise (optional tidy-up).
- Vocabulary follows `GLOSSARY.md` (server, purpose, provider, vendor, model alias, raw model string, global layer, server file, project layer, built-in variable).
- Local markdown tracker: this file is the spec; implementation tickets, if split, go under the issues folder next to it.

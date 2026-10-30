# 06: Layered config files: server file and project layer

**What to build:** On top of the shared `~/.mymcps/config.toml`, an optional server file (`~/.mymcps/image.toml`, `video.toml`, `audio.toml`) tailors one server, and an optional project layer, named only with `--project-config`, chooses models and output folders for one project. The project layer can never change where data is sent (ADR 0002). The server logs which files it loaded so the user can see the layering.

**Blocked by:** 05

**Status:** ready-for-agent

- [x] The server file is layered over the shared file for that server only; both are optional at their default location.
- [x] When `--config` or `MYMCPS_CONFIG` names a file, that file alone is the global layer and no server file is loaded.
- [x] `--project-config` adds the project layer; a missing project file fails startup; nothing is discovered automatically.
- [x] Merge order is shared file, server file, project layer: single values are overridden by the later file, models and providers are merged by name with the whole entry replaced, and tool arguments override the result.
- [x] A server file containing another server's section fails startup.
- [x] A project layer containing providers, an endpoint or key field, or model passthrough parameters fails startup; its aliases may set only the model string and a link to a global provider.
- [x] The project layer expands only built-in variables; any other `${NAME}` there fails startup.
- [x] Output folder: the section's `output_dir`, else the top-level `output_dir`, else `<temp>/mymcps/<server>`.
- [x] On startup the server writes to stderr each loaded file with its layer and path, never any value, and nothing to stdout.

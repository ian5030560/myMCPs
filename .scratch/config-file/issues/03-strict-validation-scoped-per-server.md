# 03: Strict validation, scoped to what each server uses

**What to build:** A typo in the config stops the server at startup instead of being silently ignored, and the user sees every problem in one go, each naming the file, section and field. Each server validates only what it uses: the top-level settings, the model aliases and its own section. A mistake in another server's section therefore does not stop it, while a misspelled section name is still caught.

**Blocked by:** 02

**Status:** ready-for-agent

- [x] An unknown field at the top level, in a model alias or in the server's own section fails startup.
- [x] A `*_model` field the server does not declare fails startup.
- [x] A section whose name is not a known server (for example a misspelled `[imgae]`) fails startup.
- [x] An unknown field inside another server's section does not stop this server.
- [x] All validation errors are reported together, each with file, section and field.
- [x] A config path named explicitly (`--config`, `MYMCPS_CONFIG`) that does not exist fails startup; a missing file at the default location is skipped.
- [x] Passthrough parameter contents are not validated.
- [x] Tests go through the single config seam: config text plus an environment dictionary plus a server declaration, through to the loaded settings and resolved models.

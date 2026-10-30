# 09: Docs, example config and migration notes

**What to build:** A user who reads the README and copies the example config ends up with a working setup under the new design, and a user of the old design learns exactly what changed. The project's own guidance for agents describes the new architecture.

**Blocked by:** 06, 07, 08

**Status:** ready-for-agent

- [x] The example config uses the new format: providers, model aliases, purposes with suggested models to copy (there are no defaults), the server file and project layer.
- [x] The README covers the new server names and `mymcps-<name>` commands, registration examples, the provider rules, the layers and their precedence, and variables.
- [x] The README has migration notes for every removed or renamed item: server names and commands, sections, `default_model`, `api_key_env`, `capabilities`, `allowed_dirs`, the per-field environment variables and the `stability` alias convention.
- [x] The README advises forward slashes or single-quoted strings for Windows paths, absolute paths in client registrations, LiteLLM's dedicated prefixes for self-hosted servers, and warns that `--http` has no authentication and no folder restriction.
- [x] The guidance file for agents no longer describes the old design.
- [x] Old names fail loudly, and the error points to the migration notes.
- [x] The Docker Linux check passes on Python 3.10 and 3.12.

# One package; each server declares its own configuration

All servers live in one installable package, `mymcps`. Each server is a subpackage with its own optional dependency group and its own `mymcps-<name>` command. Each server declares its name, its section fields and its purposes, and the shared core contains no server names or per-server special cases. More servers are planned, and adding one should mean adding a subpackage, not editing the core. A single package is used because pip cannot install one package from a git repository and also resolve a sibling package in the same repository as its dependency without publishing that sibling separately.

## Consequences

- One name per server is used everywhere in configuration (section, server file, project file, `${SERVER}`); only the command adds the `mymcps-` prefix, to avoid clashing with other programs on PATH.
- Each server validates only what it uses, so a mistake in one server's settings does not stop the others, and a server that needs no model never reads providers or loads LiteLLM.

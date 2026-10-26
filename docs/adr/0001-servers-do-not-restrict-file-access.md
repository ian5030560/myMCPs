# Servers do not restrict which files they read

The servers accept any local path or URL an agent passes; there is no folder allow-list. Access control is left to the agent and its MCP client, which already govern what the agent may touch. An allow-list was off by default, so it protected only users who configured it, yet it accounted for a large share of the config's rules (layer narrowing, per-server lists, environment overrides). Writes stay confined: a tool's `output_dir` may only name a subfolder of the configured output folder, and moving results elsewhere is left to the agent's own file tools.

## Consequences

- Without its own access control, a server started with `--http` must stay on localhost or sit behind an authenticating proxy. The README says so.
- An input file is uploaded to the model before anyone checks that it is really an image, video or audio file. A content-type check before upload is tracked as a separate item and needs no configuration.

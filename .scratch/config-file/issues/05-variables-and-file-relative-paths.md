# 05: Variables and file-relative paths

**What to build:** Every string value in the user's config files can use `${NAME}`: built-in variables (`CONFIG_DIR`, `CWD`, `TEMP`, `SERVER`), then environment variables, plus a leading `~` for the home directory. This lets a key stay out of the file (`api_key = "${LOCAL_API_KEY}"`) and one `output_dir` serve every server (`~/mymcps/${SERVER}`). Relative paths in a config file are relative to that file, so behaviour no longer depends on which client launched the server.

**Blocked by:** 04

**Status:** ready-for-agent

- [x] `${NAME}` expands in every string value, including nested passthrough parameters; built-in variables win over environment variables of the same name.
- [x] `$$` produces a literal `$`; expansion is single-pass and never expands its own output.
- [x] An undefined variable fails startup with file, section and field, except in `api_key`.
- [x] An `api_key` referencing an unset environment variable means "no key": `list_models` shows `key_configured: false`, and a call that fails for lack of a key names that variable.
- [x] `CONFIG_DIR` is the folder of the file the value is written in; `SERVER` is the server's name.
- [x] A relative path in a config file resolves against that file's folder; `MYMCPS_CONFIG` is used as given.
- [x] Variables are never expanded in tool arguments.

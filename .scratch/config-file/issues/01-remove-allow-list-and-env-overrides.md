# 01: Remove the folder allow-list and per-field environment overrides

**What to build:** Servers read any local path or URL an agent passes; there is no folder allow-list any more (ADR 0001). Settings come only from files: the per-field environment variables are gone and `MYMCPS_CONFIG` is the only environment variable the config reads. To keep writes bounded without the allow-list, a tool's `output_dir` argument may only name a subfolder of the configured output folder. This is a prefactor that shrinks the code the later tickets have to change.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [x] The `allowed_dirs` setting, `MYMCPS_ALLOWED_DIRS` and every read and write path check are removed; a tool reads a local file anywhere on disk.
- [x] `MYMCPS_OUTPUT_DIR`, `MYMCPS_IMAGE_MODEL`, `MYMCPS_VIDEO_MODEL`, `MYMCPS_AUDIO_MODEL` and `MYMCPS_TRANSCRIPTION_MODEL` no longer have any effect; `MYMCPS_CONFIG` still selects the config file.
- [x] A relative `output_dir` tool argument saves into that subfolder of the configured output folder.
- [x] An absolute `output_dir` tool argument, or one that escapes the output folder with `..`, is rejected with a message the agent can read.
- [x] Tests for the removed behaviour are deleted; tests that relied on an absolute `output_dir` argument are rewritten for the new rule.
- [x] Lint and the full test suite pass.

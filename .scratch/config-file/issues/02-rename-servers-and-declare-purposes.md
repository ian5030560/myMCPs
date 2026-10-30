# 02: Rename the servers and let each server declare its purposes

**What to build:** The servers become `image`, `video` and `audio`, each known by that one name in configuration and started with `mymcps-image`, `mymcps-video` and `mymcps-audio`. Each server declares its own name, its section fields and its purposes; the shared core contains no server names, default models or per-server special cases (ADR 0004). Models are configured per purpose as `<purpose>_model` in the server's section: `image` has `gen_model` and `edit_model`, `video` has `watch_model`, `audio` has `listen_model` and `transcribe_model`. There are no built-in default models.

The existing three servers are rewritten to conform, not deleted: their tools keep working, now reading their model from the purpose.

**Blocked by:** 01

**Status:** ready-for-agent

- [x] Configuring `[image] gen_model` makes `generate_image` call that model; `edit_image` uses `edit_model`.
- [x] A server with an unconfigured purpose still starts; a tool that needs it fails with a message naming the `<purpose>_model` field and the section to set it in.
- [x] Passing `model` on a tool call works even when the purpose is unconfigured.
- [x] `list_models` lists each of the server's purposes with its configured model or "not configured".
- [x] `video` and `audio` declare their purposes (they still have no tools beyond `list_models`).
- [x] Server names follow the naming rule (lowercase letters, digits, hyphens, starting with a letter) and are unique, enforced by a test.
- [x] The old names (`image_gen`, `video_watch`, `audio_listen`, `image-gen`, `video-watch`, `audio-listen`) and the default-model table no longer appear in the code, tests or package metadata; the commands are `mymcps-<name>`.
- [x] Every existing image test passes under the new names and purposes, and the stdio end-to-end test starts the server through its new command.

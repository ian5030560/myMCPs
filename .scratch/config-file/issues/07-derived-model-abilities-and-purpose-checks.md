# 07: Derived model abilities and purpose checks

**What to build:** Users no longer declare what a model can do. The servers derive it from LiteLLM's model table plus one vendor rule (Gemini chat models read video directly), treat models absent from the table as "unknown" rather than incapable, and warn at startup when a purpose's model is clearly the wrong kind, without refusing to start.

**Blocked by:** 04

**Status:** ready-for-agent

- [x] The `capabilities` field is removed and now rejected as an unknown field.
- [x] A model absent from LiteLLM's table is "unknown" on every ability, even though LiteLLM's own helpers answer "no" for unmapped models.
- [x] For each configured purpose, a known model that fails the purpose check prints a warning on stderr and the server still starts: `gen` and `edit` must produce images, `watch` must be a chat model reading video or images, `listen` must be a chat model accepting audio, `transcribe` must transcribe.
- [x] Unknown models are never warned about.
- [x] `list_models` shows each alias's derived abilities, or "unknown".
- [x] The fake LiteLLM used in tests gains a model table so known, unknown and known-but-lacking models can all be tested.

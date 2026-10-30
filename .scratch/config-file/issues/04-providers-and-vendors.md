# 04: Providers and vendors

**What to build:** Connection details live in providers, defined once and shared by several models. Every model resolves to exactly one provider: the one its alias links to, else the provider named after its vendor, else a built-in default for that vendor that uses LiteLLM's standard environment variables. A provider knows which vendor's API it speaks, and every behaviour that differs per vendor reads it from the provider. Keys are a single `api_key` field (literal values in this ticket; `${VAR}` arrives in 05).

The image server is rewritten to conform: its vendor checks read the provider's vendor, and the Stability connection comes from provider resolution instead of the special alias named `stability`.

**Blocked by:** 03

**Status:** ready-for-agent

- [x] A provider named after a vendor (for example `[providers.stability]`) applies to every model of that vendor, including raw model strings passed by the agent.
- [x] A provider whose name is not a vendor applies only to aliases that link to it; a raw `openai/...` string never reaches it.
- [x] An explicit link beats the provider named after the vendor.
- [x] A link to an undefined provider, and a link to a provider that states a different vendor, fail startup.
- [x] A provider's vendor defaults to its name when that is a known vendor, otherwise it is stated or taken from the models that link to it; linked models that disagree fail startup.
- [x] Passthrough parameters merge provider first, then model, with the model winning on the same key.
- [x] Alias names containing `/` fail startup.
- [x] `api_key` replaces `api_key_env`, which is now rejected as an unknown field; a literal key produces no warning.
- [x] Image editing paths, Stability looping, file upload routing and missing-key hints all read the provider's vendor.
- [x] The special `stability` alias is gone; `stability_edit` is registered only when a key is reachable for `stability/...` models (a key on the resolving provider, or `STABILITY_API_KEY`).
- [x] `list_models` shows each configured alias with its model string, provider name, vendor and `key_configured`, and never a key or endpoint. `key_configured` is false only when a key is expected but unavailable.
- [x] Every existing image test passes after being updated for providers.

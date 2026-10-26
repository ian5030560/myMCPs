# mymcps

MCP servers that give AI agents media abilities (today: images, video and audio), sharing one configuration language. This glossary covers that shared vocabulary.

## Language

**Server**:
One program an agent connects to, known by one short name (`image`, `video`, `audio`) everywhere in configuration.
_Avoid_: Service, function, tool (a tool is one thing a server offers)

**Purpose**:
A job a server needs a model for, such as `image`'s `gen` or `audio`'s `transcribe`; each is configured as `<purpose>_model` in that server's section.
_Avoid_: Role, task, default model

### Models and connections

**Vendor**:
The company or API family that serves a model, written as the part of a model string before the slash (`openai`, `gemini`, `stability`).
_Avoid_: Vendor prefix, provider prefix

**Provider**:
A named set of connection details (which vendor's API it speaks, where requests go, which key they carry) that several models share. Every model has exactly one provider; one named after a vendor applies to all of that vendor's models, any other only to models that link to it.
_Avoid_: Backend, endpoint profile, connection

**Model alias**:
A short name for a model string, optionally linked to a provider.
_Avoid_: Model name, preset, profile

**Raw model string**:
A `vendor/model` identifier given directly instead of through a model alias.
_Avoid_: Model id, bare model

### Configuration layers

**Global layer**:
The user's own config: a shared file for all servers plus an optional server file for each. It alone defines providers and keys.
_Avoid_: User config, system config, base config

**Server file**:
The part of the global layer that applies to one server only.
_Avoid_: Function file, per-server config

**Project layer**:
An optional config file named explicitly when a server is registered, which can choose models and output locations for one project but can never change where data is sent.
_Avoid_: Local config, workspace config

**Built-in variable**:
A `${NAME}` placeholder defined by the config language itself (config folder, working directory, temp folder, server name), as opposed to an environment variable.
_Avoid_: Path variable, placeholder, macro

### Image editing

**Mask**:
A black-and-white image the same shape as the image being edited; white marks the area to change and black the area to keep.
_Avoid_: Stencil, alpha map

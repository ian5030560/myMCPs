# All model calls go through LiteLLM, pinned to an exact version

Every model call goes through LiteLLM, because it alone covers what the servers need behind one interface: image generation and editing across OpenAI, Gemini and Stability (including Stability's per-operation endpoints), Gemini's native video and audio input, transcription, and any OpenAI-compatible endpoint. LiteLLM was compromised on PyPI on 2026-03-24 when malicious releases 1.82.7 and 1.82.8 were published. To guard against that kind of attack, the project pins LiteLLM to one exact version and pins every runtime dependency, direct and transitive, in `requirements.txt`. That file is used as a pip constraints file, which supports no hashes, so the protection rests on the pinned versions rather than on hash checks. LiteLLM is imported in exactly one place, lazily, with stdout redirected so it can never corrupt the stdio transport.

## Considered Options

- **The vendors' own SDKs** (`openai`, `google-genai`, plain HTTP for Stability): lighter and fully controlled, but every vendor's quirks and the multi-vendor abstraction would be ours to write and maintain.
- **Other unified libraries** (any-llm, aisuite, Pydantic AI): at the time they covered chat only, or lacked image generation, Stability and transcription.

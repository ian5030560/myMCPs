"""What the core knows about vendors: the API families LiteLLM routes to.

A vendor is the part of a model string before the slash (``openai/gpt-image-2`` -> ``openai``).
Nothing here imports LiteLLM, so reading a config never loads it.
"""

from __future__ import annotations

# Vendors a provider may be named after (`[providers.stability]` applies to every stability/...
# model). A provider with any other name is reachable only through an explicit link.
KNOWN_VENDORS = frozenset({
    "openai", "azure", "gemini", "vertex_ai", "stability", "anthropic", "bedrock", "mistral",
    "groq", "cohere", "deepseek", "xai", "openrouter", "together_ai", "fireworks_ai",
    "perplexity", "ollama", "ollama_chat", "hosted_vllm", "lm_studio", "huggingface",
})

# LiteLLM's standard key variable for the vendors we can name one for.
STANDARD_KEY_VARS = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "stability": "STABILITY_API_KEY",
}


def vendor_of(model: str) -> str | None:
    """The vendor written in a model string, or None for a bare name like ``gpt-4o``
    (only LiteLLM can say which vendor serves those)."""
    head, sep, _ = model.partition("/")
    return head if sep and head else None

from mymcps.core.config import ModelSpec, Settings
from mymcps.core.models import ModelRegistry


def make(llm, **kw):
    settings = Settings(
        models={"local-vl": ModelSpec(model="openai/qwen", api_base="http://x/v1",
                                      api_key_env="LOCAL_KEY", capabilities=["vision"],
                                      extra={"timeout": 9})},
        **kw)
    return ModelRegistry(settings, llm, environ={"LOCAL_KEY": "secret"})


def test_alias_resolution(llm):
    m = make(llm).resolve("video_watch", "local-vl")
    assert m.model == "openai/qwen" and m.provider == "openai"
    assert m.call_kwargs() == {"timeout": 9, "api_base": "http://x/v1", "api_key": "secret"}


def test_direct_litellm_string(llm):
    m = make(llm).resolve("video_watch", "gemini/gemini-2.5-flash")
    assert m.provider == "gemini" and m.call_kwargs() == {}


def test_server_default_and_builtin_default(llm):
    reg = make(llm, video_watch={"default_model": "local-vl"})
    assert reg.resolve("video_watch").alias == "local-vl"
    assert reg.resolve("image_gen").model == "openai/gpt-image-1"


def test_transcription_purpose(llm):
    reg = make(llm)
    assert reg.resolve("audio_listen", purpose="transcription").model == "openai/whisper-1"
    reg = make(llm, audio_listen={"transcription_model": "groq/whisper-large-v3"})
    assert reg.resolve("audio_listen", purpose="transcription").model == "groq/whisper-large-v3"


def test_supports_prefers_declaration_then_litellm(llm):
    local = make(llm).resolve("video_watch", "local-vl")
    assert local.supports("vision") is True                # declared
    assert local.supports("audio_input") is None           # litellm raised -> unknown
    gemini = make(llm).resolve("video_watch", "gemini/x")
    assert gemini.supports("vision") is True               # from litellm table
    assert make(llm).resolve("video_watch", "openai/x").supports("vision") is False


def test_describe_hides_secrets_and_marks_defaults(llm):
    rows = make(llm, video_watch={"default_model": "local-vl"}).describe("video_watch")
    flat = repr(rows)
    assert "secret" not in flat and "http://x" not in flat and "LOCAL_KEY" not in flat
    local = next(r for r in rows if r["alias"] == "local-vl")
    assert local["default_for"] == ["default"]

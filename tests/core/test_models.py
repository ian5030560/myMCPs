import pytest

from mymcps.core.abilities import HEARS_AUDIO, PRODUCES_IMAGES, TRANSCRIBES, WATCHES_VIDEO
from mymcps.core.config import ModelSpec, ProviderSpec, Settings
from mymcps.core.errors import PurposeNotConfiguredError
from mymcps.core.models import ModelRegistry
from mymcps.core.spec import Purpose, ServerSpec

SERVER = ServerSpec("demo", purposes=(
    Purpose("main", "the main job"),
    Purpose("extra", "a second job"),
))


def make(llm, sections=None, environ=None, providers=None, models=None, **kw):
    settings = Settings(
        providers=providers if providers is not None else {
            "local": ProviderSpec(vendor="openai", api_base="http://x/v1", api_key="secret",
                                  extra={"timeout": 5, "retries": 1}),
        },
        models=models if models is not None else {
            "local-vl": ModelSpec(model="openai/qwen", provider="local",
                                  extra={"timeout": 9}),
        },
        sections=sections or {},
        **kw)
    return ModelRegistry(settings, llm, SERVER, environ=environ or {})


# ── purposes ─────────────────────────────────────────────────────────────


def test_purpose_uses_the_configured_model(llm):
    reg = make(llm, sections={"demo": {"main_model": "local-vl", "extra_model": "gemini/x"}})
    assert reg.resolve("main").alias == "local-vl"
    assert reg.resolve("extra").model == "gemini/x"


def test_model_argument_beats_the_configured_model(llm):
    reg = make(llm, sections={"demo": {"main_model": "local-vl"}})
    assert reg.resolve("main", "gemini/other").model == "gemini/other"


def test_unconfigured_purpose_names_the_field_and_the_section(llm):
    with pytest.raises(PurposeNotConfiguredError) as err:
        make(llm).resolve("main")
    message = str(err.value)
    assert "main_model" in message and "[demo]" in message and "the main job" in message


def test_unconfigured_purpose_still_works_when_a_model_is_passed(llm):
    assert make(llm).resolve("main", "openai/gpt-image-2").model == "openai/gpt-image-2"


def test_there_are_no_built_in_default_models(llm):
    # Another server's section configures nothing for this one.
    reg = make(llm, sections={"other": {"main_model": "local-vl"}})
    with pytest.raises(PurposeNotConfiguredError):
        reg.resolve("main")


def test_unknown_purpose_is_a_programming_error(llm):
    with pytest.raises(KeyError, match="no purpose 'nope'"):
        make(llm).resolve("nope")


# ── which provider a model gets ──────────────────────────────────────────


def test_an_alias_linked_to_a_provider_uses_its_connection(llm):
    m = make(llm).resolve_model("local-vl")
    assert m.model == "openai/qwen"
    assert (m.provider.name, m.vendor) == ("local", "openai")
    assert m.call_kwargs() == {"timeout": 9, "retries": 1, "api_base": "http://x/v1",
                               "api_key": "secret"}


def test_a_raw_string_without_any_provider_gets_the_built_in_default(llm):
    m = make(llm).resolve_model("gemini/gemini-2.5-flash")
    assert (m.provider.name, m.vendor) == ("gemini", "gemini")
    assert m.call_kwargs() == {}


def test_a_provider_named_after_a_vendor_applies_to_raw_strings_of_that_vendor(llm):
    providers = {"stability": ProviderSpec(api_base="http://proxy/stab", api_key="k")}
    m = make(llm, providers=providers).resolve_model("stability/sd3.5-large")
    assert m.provider.name == "stability" and m.vendor == "stability"
    assert m.call_kwargs() == {"api_base": "http://proxy/stab", "api_key": "k"}


def test_a_provider_named_after_a_vendor_applies_to_aliases_without_a_link(llm):
    providers = {"stability": ProviderSpec(api_base="http://proxy/stab")}
    models = {"sd": ModelSpec(model="stability/sd3.5-large")}
    m = make(llm, providers=providers, models=models).resolve_model("sd")
    assert m.call_kwargs() == {"api_base": "http://proxy/stab"}


def test_a_provider_named_after_a_vendor_does_not_touch_other_vendors(llm):
    providers = {"stability": ProviderSpec(api_base="http://proxy/stab", api_key="k")}
    assert make(llm, providers=providers).resolve_model("openai/gpt-image-2").call_kwargs() == {}


def test_a_provider_with_another_name_is_never_applied_to_a_raw_string(llm):
    # `local` speaks openai, but a raw openai/... string must still reach the real OpenAI.
    m = make(llm).resolve_model("openai/gpt-image-2")
    assert m.provider.name == "openai" and m.call_kwargs() == {}


def test_an_explicit_link_beats_the_provider_named_after_the_vendor(llm):
    providers = {
        "openai": ProviderSpec(api_key="official"),
        "local": ProviderSpec(vendor="openai", api_base="http://x/v1", api_key="mine"),
    }
    models = {"q": ModelSpec(model="openai/qwen", provider="local"),
              "g": ModelSpec(model="openai/gpt-image-2")}
    reg = make(llm, providers=providers, models=models)
    assert reg.resolve_model("q").call_kwargs() == {"api_base": "http://x/v1", "api_key": "mine"}
    assert reg.resolve_model("g").call_kwargs() == {"api_key": "official"}
    assert reg.resolve_model("openai/other").call_kwargs() == {"api_key": "official"}


def test_a_name_without_a_slash_gets_the_vendor_litellm_routes_it_to(llm):
    m = make(llm).resolve_model("gpt-image-1")      # the fake routes bare names to openai
    assert m.vendor == "openai" and m.provider.name == "openai"


def test_a_providers_vendor_is_what_behaviour_reads(llm):
    models = {"q": ModelSpec(model="hosted_vllm/qwen", provider="local")}
    m = make(llm, models=models).resolve_model("q")
    assert m.vendor == "openai"         # the provider speaks the OpenAI API


# ── parameters ───────────────────────────────────────────────────────────


def test_passthrough_parameters_merge_provider_first_and_the_model_wins(llm):
    m = make(llm).resolve_model("local-vl")
    assert m.extra == {"timeout": 9, "retries": 1}


def test_a_model_without_parameters_gets_the_providers(llm):
    models = {"m": ModelSpec(model="openai/x", provider="local")}
    assert make(llm, models=models).resolve_model("m").extra == {"timeout": 5, "retries": 1}


def test_an_empty_literal_key_is_no_key(llm):
    providers = {"openai": ProviderSpec(api_key="")}
    assert "api_key" not in make(llm, providers=providers).resolve_model("openai/x").call_kwargs()


# ── abilities ────────────────────────────────────────────────────────────


def abilities(llm, model):
    return make(llm).resolve_model(model).abilities()


def test_a_model_absent_from_the_table_is_unknown_on_every_count(llm):
    # LiteLLM's own supports_vision would say "no" for these; here they are unknown.
    for name in ("openai/qwen", "local-vl", "hosted_vllm/brand-new", "gemini/not-yet-listed"):
        resolved = make(llm).resolve_model(name)
        assert resolved.abilities() is None
        assert resolved.supports("vision") is None and resolved.supports("chat") is None


def test_abilities_come_from_the_table(llm):
    assert abilities(llm, "gemini/gemini-2.5-flash") == {
        "chat", "vision", "audio_input", "video_input"}   # video: the Gemini rule
    assert abilities(llm, "gpt-4o") == {"chat", "vision"}
    assert abilities(llm, "gpt-image-2") == {"image_output", "vision"}
    assert abilities(llm, "stability/inpaint") == {"image_output"}
    assert abilities(llm, "whisper-1") == {"transcription"}


def test_openai_models_are_found_with_or_without_their_prefix(llm):
    assert abilities(llm, "openai/gpt-4o") == abilities(llm, "gpt-4o") == {"chat", "vision"}


def test_a_known_model_lacking_an_ability_is_known_not_to_have_it(llm):
    plain = make(llm).resolve_model("gpt-3.5-turbo")
    assert plain.abilities() == {"chat"}
    assert plain.supports("vision") is False and plain.supports("chat") is True


def test_the_gemini_video_rule_applies_to_chat_models_only(llm):
    assert "video_input" not in abilities(llm, "gemini/gemini-3.1-flash-image")
    assert "video_input" not in abilities(llm, "gpt-4o")


# ── purpose checks ───────────────────────────────────────────────────────

CHECKED = ServerSpec("demo", purposes=(
    Purpose("draw", "drawing", PRODUCES_IMAGES),
    Purpose("watch", "watching", WATCHES_VIDEO),
    Purpose("listen", "listening", HEARS_AUDIO),
    Purpose("transcribe", "transcribing", TRANSCRIBES),
    Purpose("free", "no requirement"),
))


def warnings(llm, **fields):
    settings = Settings(sections={"demo": fields})
    return ModelRegistry(settings, llm, CHECKED, environ={}).check_purposes()


@pytest.mark.parametrize("fields", [
    {"draw_model": "gpt-image-2"},
    {"draw_model": "stability/inpaint"},
    {"watch_model": "gemini/gemini-2.5-flash"},
    {"watch_model": "gpt-4o"},
    {"listen_model": "gemini/gemini-2.5-flash"},
    {"transcribe_model": "openai/whisper-1"},
    {"free_model": "whisper-1"},
])
def test_a_model_of_the_right_kind_passes_its_purpose_check(llm, fields):
    assert warnings(llm, **fields) == []


@pytest.mark.parametrize("field,model,needle", [
    ("draw_model", "gpt-4o", "produces images"),
    ("watch_model", "gpt-image-2", "reads video or images"),
    ("watch_model", "gpt-3.5-turbo", "reads video or images"),
    ("listen_model", "gpt-4o", "accepts audio"),
    ("transcribe_model", "gpt-4o", "transcribes speech"),
])
def test_a_known_model_of_the_wrong_kind_is_warned_about(llm, field, model, needle):
    [warning] = warnings(llm, **{field: model})
    assert field in warning and model in warning and needle in warning


def test_unknown_models_are_never_warned_about(llm):
    assert warnings(llm, draw_model="openai/qwen", watch_model="hosted_vllm/new",
                    listen_model="gemini/unlisted", transcribe_model="foo/bar") == []


def test_aliases_are_checked_through_what_they_point_at(llm):
    models = {"chat": ModelSpec(model="gpt-4o"), "mine": ModelSpec(model="openai/qwen")}
    settings = Settings(models=models, sections={"demo": {"draw_model": "chat",
                                                          "watch_model": "mine"}})
    found = ModelRegistry(settings, llm, CHECKED, environ={}).check_purposes()
    assert len(found) == 1 and "`chat`" in found[0]


def test_unconfigured_purposes_are_not_checked(llm):
    assert warnings(llm) == []


# ── keys ─────────────────────────────────────────────────────────────────


def test_a_key_on_the_provider_counts(llm):
    reg = make(llm)
    assert reg.has_key(reg.resolve_model("local-vl"))


def test_the_vendors_standard_variable_counts(llm):
    assert not make(llm).has_key(make(llm).resolve_model("stability/fast"))
    reg = make(llm, environ={"STABILITY_API_KEY": "k"})
    assert reg.has_key(reg.resolve_model("stability/fast"))


def test_a_key_on_another_vendors_provider_does_not_count(llm):
    reg = make(llm)
    assert not reg.has_key(reg.resolve_model("gemini/x"))


@pytest.mark.parametrize("model,environ,expected", [
    ("local-vl", {}, True),                                  # has its own key
    ("openai/gpt-image-2", {}, False),                       # key expected, not there
    ("openai/gpt-image-2", {"OPENAI_API_KEY": "k"}, True),
    ("gemini/x", {}, False),
    ("anthropic/claude", {}, True),                          # no standard variable we know of
    ("hosted_vllm/qwen", {}, True),
])
def test_key_configured_is_false_only_when_a_key_is_expected_but_missing(
        llm, model, environ, expected):
    reg = make(llm, environ=environ)
    assert reg.key_configured(reg.resolve_model(model)) is expected


def test_a_self_hosted_endpoint_without_a_key_is_not_reported_as_missing(llm):
    providers = {"local": ProviderSpec(vendor="openai", api_base="http://x/v1")}
    models = {"q": ModelSpec(model="openai/qwen", provider="local")}
    reg = make(llm, providers=providers, models=models)
    assert reg.key_configured(reg.resolve_model("q")) is True


# ── list_models ──────────────────────────────────────────────────────────


def test_describe_lists_every_purpose(llm):
    info = make(llm, sections={"demo": {"main_model": "local-vl"}}).describe()
    by_name = {p["purpose"]: p for p in info["purposes"]}
    assert by_name["main"] == {
        "purpose": "main", "field": "main_model", "summary": "the main job",
        "configured": True, "model": "local-vl"}
    assert by_name["extra"]["model"] == "not configured" and by_name["extra"]["configured"] is False


def test_describe_marks_which_purposes_use_an_alias(llm):
    info = make(llm, sections={"demo": {"main_model": "local-vl", "extra_model": "local-vl"}}
                ).describe()
    assert info["models"][0]["alias"] == "local-vl"
    assert info["models"][0]["used_for"] == ["main", "extra"]


def test_describe_shows_provider_vendor_and_whether_a_key_is_configured(llm):
    models = {"linked": ModelSpec(model="openai/qwen", provider="local"),
              "plain": ModelSpec(model="gemini/x")}
    info = make(llm, models=models).describe()
    by_alias = {m["alias"]: m for m in info["models"]}
    assert by_alias["linked"] == {
        "alias": "linked", "model": "openai/qwen", "provider": "local", "vendor": "openai",
        "key_configured": True, "abilities": "unknown", "used_for": []}
    assert (by_alias["plain"]["provider"], by_alias["plain"]["vendor"]) == ("gemini", "gemini")
    assert by_alias["plain"]["key_configured"] is False


def test_describe_hides_keys_and_endpoints(llm):
    flat = repr(make(llm, sections={"demo": {"main_model": "local-vl"}}).describe())
    assert "secret" not in flat and "http://x" not in flat

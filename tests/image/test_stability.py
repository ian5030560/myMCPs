import io

import pytest
from PIL import Image

from conftest import image_response, png_bytes
from mymcps.core.errors import MediaToolError
from mymcps.image.stability import OPERATIONS, StabilityEditor


def test_operation_table_matches_litellm_models():
    assert {op.model for op in OPERATIONS.values()} == {
        "stability/remove-background", "stability/erase", "stability/outpaint",
        "stability/search-and-replace", "stability/search-and-recolor",
        "stability/fast", "stability/conservative"}


def test_not_available_without_a_key(make_ctx):
    assert not StabilityEditor.available(make_ctx(environ={}))


def test_available_with_the_standard_environment_variable(make_ctx):
    assert StabilityEditor.available(make_ctx(environ={"STABILITY_API_KEY": "k"}))


def test_available_with_a_key_on_the_provider_named_stability(make_ctx):
    assert StabilityEditor.available(make_ctx(providers={"stability": {"api_key": "k"}}))


def test_a_key_on_another_provider_does_not_make_it_available(make_ctx):
    openai_only = make_ctx(providers={"openai": {"api_key": "k"}})
    assert not StabilityEditor.available(openai_only)
    # A provider with another name is reachable only through a link; raw stability/... strings
    # never go through it.
    linked_only = make_ctx(
        providers={"corp": {"vendor": "stability", "api_key": "k"}},
        models={"s": {"model": "stability/sd3.5-large", "provider": "corp"}})
    assert not StabilityEditor.available(linked_only)


@pytest.mark.parametrize("operation,kwargs,needle", [
    ("search_and_replace", {"prompt": "cat"}, "search_prompt"),
    ("search_and_replace", {"search_prompt": "dog"}, "prompt"),
    ("search_and_recolor", {"prompt": "red"}, "select_prompt"),
    ("upscale_conservative", {}, "prompt"),
    ("outpaint", {}, "left, right, top, bottom"),
    ("nonsense", {}, "Unknown operation"),
])
async def test_missing_parameters_are_explained(
        ctx, fake_litellm, photo, operation, kwargs, needle):
    with pytest.raises(MediaToolError, match=needle):
        await StabilityEditor(ctx).run(operation, str(photo), **kwargs)
    assert fake_litellm.calls == []


async def test_remove_background(ctx, fake_litellm, photo):
    fake_litellm.response = image_response(png_bytes())
    paths = await StabilityEditor(ctx).run("remove_background", str(photo), prompt="ignored")
    kw = fake_litellm.calls[0][1]
    assert kw["model"] == "stability/remove-background" and kw["prompt"] == ""
    assert set(kw) == {"model", "image", "prompt", "drop_params"}     # nothing extra is sent
    assert paths[0].name.startswith("stab-remove_background-")


async def test_outpaint_sends_only_the_directions_given(ctx, fake_litellm, photo):
    fake_litellm.response = image_response(png_bytes())
    await StabilityEditor(ctx).run("outpaint", str(photo), left=200, bottom=100, prompt="a beach")
    kw = fake_litellm.calls[0][1]
    assert (kw["left"], kw["bottom"], kw["prompt"]) == (200, 100, "a beach")
    assert "right" not in kw and "top" not in kw


async def test_search_and_replace_parameters(ctx, fake_litellm, photo):
    fake_litellm.response = image_response(png_bytes())
    await StabilityEditor(ctx).run("search_and_replace", str(photo), prompt="a fox",
                                   search_prompt="the dog", negative_prompt="blurry", left=5)
    kw = fake_litellm.calls[0][1]
    assert kw["model"] == "stability/search-and-replace"
    assert (kw["prompt"], kw["search_prompt"], kw["negative_prompt"]) == (
        "a fox", "the dog", "blurry")
    assert "left" not in kw          # not an input of this operation: ignored


async def test_erase_converts_the_mask(ctx, fake_litellm, photo, mask_file):
    fake_litellm.response = image_response(png_bytes())
    await StabilityEditor(ctx).run("erase", str(photo), mask=str(mask_file), grow_mask=3)
    kw = fake_litellm.calls[0][1]
    assert kw["grow_mask"] == 3 and Image.open(io.BytesIO(kw["mask"])).mode == "L"


async def test_the_provider_named_stability_supplies_the_connection(
        make_ctx, fake_litellm, photo):
    ctx = make_ctx(providers={"stability": {"api_base": "http://proxy/stab", "api_key": "k",
                                            "extra": {"timeout": 7}}})
    fake_litellm.response = image_response(png_bytes())
    await StabilityEditor(ctx).run("upscale_fast", str(photo))
    kw = fake_litellm.calls[0][1]
    assert kw["model"] == "stability/fast"
    assert (kw["api_base"], kw["api_key"], kw["timeout"]) == ("http://proxy/stab", "k", 7)


async def test_an_alias_called_stability_is_just_an_alias(make_ctx, fake_litellm, photo):
    ctx = make_ctx(models={"stability": {"model": "openai/other", "extra": {"timeout": 1}}})
    fake_litellm.response = image_response(png_bytes())
    await StabilityEditor(ctx).run("upscale_fast", str(photo))
    assert "timeout" not in fake_litellm.calls[0][1]

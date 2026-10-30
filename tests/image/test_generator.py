from conftest import image_response, png_bytes
from mymcps.image.generator import ImageGenerator


async def test_forwards_only_given_params(ctx, fake_litellm):
    fake_litellm.response = image_response(png_bytes())
    paths = await ImageGenerator(ctx).generate("a cat")
    name, kw = fake_litellm.calls[0]
    assert name == "aimage_generation"
    assert kw == {"model": "openai/gpt-image-2", "prompt": "a cat", "drop_params": True}
    assert len(paths) == 1 and paths[0].exists()


async def test_forwards_size_quality_n_and_model(ctx, fake_litellm):
    fake_litellm.response = image_response(png_bytes(), png_bytes())
    paths = await ImageGenerator(ctx).generate(
        "a cat", model="gemini/gemini-3.1-flash-image", n=2, size="1024x1024", quality="high")
    kw = fake_litellm.calls[0][1]
    assert kw["model"] == "gemini/gemini-3.1-flash-image"
    assert (kw["n"], kw["size"], kw["quality"]) == (2, "1024x1024", "high")
    assert len(fake_litellm.calls) == 1 and len(paths) == 2


async def test_stability_is_called_once_per_image(ctx, fake_litellm):
    fake_litellm.response = image_response(png_bytes())
    paths = await ImageGenerator(ctx).generate("a cat", model="stability/sd3.5-large", n=3)
    assert len(fake_litellm.calls) == 3
    assert all("n" not in kw for _, kw in fake_litellm.calls)
    assert len({p.name for p in paths}) == 3


async def test_output_dir_override(ctx, fake_litellm, tmp_path):
    fake_litellm.response = image_response(png_bytes())
    paths = await ImageGenerator(ctx).generate("a cat", output_dir="shots")
    assert paths[0].parent == (tmp_path / "out" / "shots").resolve()


async def test_model_alias_supplies_connection_settings(make_ctx, fake_litellm):
    ctx = make_ctx(providers={"local": {"vendor": "openai", "api_base": "http://x/v1"}},
                   models={"mine": {"model": "openai/local-img", "provider": "local",
                                    "extra": {"timeout": 9}}})
    fake_litellm.response = image_response(png_bytes())
    await ImageGenerator(ctx).generate("a cat", model="mine")
    kw = fake_litellm.calls[0][1]
    assert (kw["model"], kw["api_base"], kw["timeout"]) == ("openai/local-img", "http://x/v1", 9)


async def test_a_bad_output_dir_is_rejected_before_any_model_call(ctx, fake_litellm, tmp_path):
    import pytest

    from mymcps.core.errors import AccessDeniedError

    for bad in ("../elsewhere", str(tmp_path.resolve())):
        with pytest.raises(AccessDeniedError):
            await ImageGenerator(ctx).generate("a cat", output_dir=bad)
    assert fake_litellm.calls == []

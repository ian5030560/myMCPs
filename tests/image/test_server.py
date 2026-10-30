from mcp import Client
from mcp.types import ImageContent, TextContent

from conftest import image_response, png_bytes
from mymcps.image.server import ImageServer


def tool_names(tools):
    return {t.name for t in tools.tools}


async def test_tools_without_stability_key(make_ctx):
    async with Client(ImageServer(make_ctx(environ={})).mcp) as client:
        assert tool_names(await client.list_tools()) == {
            "list_models", "generate_image", "edit_image"}


async def test_stability_tool_appears_with_a_key_on_the_stability_provider(make_ctx):
    ctx = make_ctx(environ={}, providers={"stability": {"api_key": "k"}})
    async with Client(ImageServer(ctx).mcp) as client:
        assert "stability_edit" in tool_names(await client.list_tools())


async def test_stability_tool_stays_hidden_when_only_a_linked_provider_has_the_key(make_ctx):
    ctx = make_ctx(environ={}, providers={"corp": {"vendor": "stability", "api_key": "k"}},
                   models={"s": {"model": "stability/sd3.5-large", "provider": "corp"}})
    async with Client(ImageServer(ctx).mcp) as client:
        assert "stability_edit" not in tool_names(await client.list_tools())


async def test_stability_tool_appears_with_a_key(make_ctx):
    async with Client(ImageServer(make_ctx(environ={"STABILITY_API_KEY": "dummy"})).mcp) as client:
        tools = await client.list_tools()
        assert "stability_edit" in tool_names(tools)
        tool = next(t for t in tools.tools if t.name == "stability_edit")
        schema = tool.input_schema
        assert schema["required"] == ["operation", "image"]
        assert set(schema["properties"]["operation"]["enum"]) == {
            "remove_background", "erase", "outpaint", "search_and_replace",
            "search_and_recolor", "upscale_fast", "upscale_conservative"}
        assert "search_and_replace" in tool.description


async def test_generate_image_returns_paths_and_a_preview(make_ctx, fake_litellm):
    fake_litellm.response = image_response(png_bytes((300, 200)))
    ctx = make_ctx()
    async with Client(ImageServer(ctx).mcp) as client:
        result = await client.call_tool("generate_image", {"prompt": "a cat"})
    assert not result.is_error
    texts = [c for c in result.content if isinstance(c, TextContent)]
    images = [c for c in result.content if isinstance(c, ImageContent)]
    assert len(images) == 1 and images[0].mime_type == "image/jpeg"
    saved = [line for line in texts[0].text.splitlines() if line.endswith(".png")]
    assert len(saved) == 1 and saved[0].startswith(str(ctx.outputs.directory()))


async def test_tool_errors_are_reported_to_the_agent(make_ctx, fake_litellm, photo):
    async with Client(ImageServer(make_ctx()).mcp) as client:
        result = await client.call_tool("edit_image", {
            "image": str(photo), "prompt": "x", "model": "stability/sd3.5-large"})
    assert result.is_error
    assert "needs a mask" in result.content[0].text
    assert fake_litellm.calls == []


async def test_descriptions_explain_masks_and_sizes(make_ctx):
    async with Client(ImageServer(make_ctx()).mcp) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert "WHITE" in tools["edit_image"].description
    assert "stability" in tools["edit_image"].description
    assert "1024x1024" in tools["generate_image"].description


async def test_output_dir_argument_saves_into_a_subfolder(make_ctx, fake_litellm, tmp_path):
    fake_litellm.response = image_response(png_bytes())
    async with Client(ImageServer(make_ctx()).mcp) as client:
        result = await client.call_tool(
            "generate_image", {"prompt": "a cat", "output_dir": "logos"})
    assert not result.is_error
    saved = list((tmp_path / "out" / "logos").glob("img-*.png"))
    assert len(saved) == 1


async def test_absolute_or_escaping_output_dir_is_rejected_for_the_agent(
        make_ctx, fake_litellm, tmp_path):
    fake_litellm.response = image_response(png_bytes())
    async with Client(ImageServer(make_ctx()).mcp) as client:
        absolute = await client.call_tool(
            "generate_image", {"prompt": "x", "output_dir": str(tmp_path / "elsewhere")})
        escaping = await client.call_tool(
            "generate_image", {"prompt": "x", "output_dir": "../elsewhere"})
    assert absolute.is_error and "relative" in absolute.content[0].text
    assert escaping.is_error and "escapes" in escaping.content[0].text
    assert not (tmp_path / "elsewhere").exists()


# ── purposes (ticket 02) ─────────────────────────────────────────────────


async def test_gen_model_and_edit_model_are_used_by_their_tools(
        make_ctx, fake_litellm, photo):
    fake_litellm.response = image_response(png_bytes())
    ctx = make_ctx(sections={"image": {"gen_model": "openai/gen-x", "edit_model": "gemini/edit-y"}})
    async with Client(ImageServer(ctx).mcp) as client:
        await client.call_tool("generate_image", {"prompt": "a cat"})
        await client.call_tool("edit_image", {"image": str(photo), "prompt": "make it night"})
    models = [kw["model"] for _, kw in fake_litellm.calls]
    assert models == ["openai/gen-x", "gemini/edit-y"]


async def test_a_server_with_unconfigured_purposes_still_starts(make_ctx):
    async with Client(ImageServer(make_ctx(sections={})).mcp) as client:
        tools = await client.list_tools()
    assert {"generate_image", "edit_image", "list_models"} <= {t.name for t in tools.tools}


async def test_an_unconfigured_purpose_fails_naming_the_field_and_the_section(
        make_ctx, fake_litellm, photo):
    async with Client(ImageServer(make_ctx(sections={})).mcp) as client:
        gen = await client.call_tool("generate_image", {"prompt": "a cat"})
        edit = await client.call_tool("edit_image", {"image": str(photo), "prompt": "x"})
    assert gen.is_error and "gen_model" in gen.content[0].text
    assert "[image]" in gen.content[0].text
    assert edit.is_error and "edit_model" in edit.content[0].text
    assert fake_litellm.calls == []


async def test_only_the_unconfigured_purpose_fails(make_ctx, fake_litellm, photo):
    fake_litellm.response = image_response(png_bytes())
    ctx = make_ctx(sections={"image": {"gen_model": "openai/gen-x"}})
    async with Client(ImageServer(ctx).mcp) as client:
        ok = await client.call_tool("generate_image", {"prompt": "a cat"})
        bad = await client.call_tool("edit_image", {"image": str(photo), "prompt": "x"})
    assert not ok.is_error
    assert bad.is_error and "edit_model" in bad.content[0].text


async def test_passing_model_works_even_when_the_purpose_is_unconfigured(
        make_ctx, fake_litellm, photo):
    fake_litellm.response = image_response(png_bytes())
    async with Client(ImageServer(make_ctx(sections={})).mcp) as client:
        gen = await client.call_tool(
            "generate_image", {"prompt": "a cat", "model": "openai/gpt-image-2"})
        edit = await client.call_tool(
            "edit_image", {"image": str(photo), "prompt": "x", "model": "gemini/some-model"})
    assert not gen.is_error and not edit.is_error
    assert [kw["model"] for _, kw in fake_litellm.calls] == [
        "openai/gpt-image-2", "gemini/some-model"]


async def test_list_models_shows_each_purpose_and_its_model(make_ctx):
    ctx = make_ctx(sections={"image": {"gen_model": "openai/gen-x"}})
    async with Client(ImageServer(ctx).mcp) as client:
        result = await client.call_tool("list_models", {})
    assert not result.is_error
    purposes = {p["purpose"]: p for p in result.structured_content["purposes"]}
    assert purposes["gen"]["model"] == "openai/gen-x" and purposes["gen"]["configured"] is True
    assert purposes["edit"]["model"] == "not configured"
    assert purposes["edit"]["configured"] is False
    assert purposes["edit"]["field"] == "edit_model"


async def test_list_models_shows_provider_vendor_and_key_state_but_no_secrets(make_ctx):
    ctx = make_ctx(
        environ={},
        providers={"local": {"vendor": "openai", "api_base": "http://secret-host/v1",
                             "api_key": "sk-secret"}},
        models={"mine": {"model": "openai/qwen", "provider": "local"},
                "cloud": {"model": "gemini/x"}})
    async with Client(ImageServer(ctx).mcp) as client:
        result = await client.call_tool("list_models", {})
    by_alias = {m["alias"]: m for m in result.structured_content["models"]}
    assert (by_alias["mine"]["provider"], by_alias["mine"]["vendor"]) == ("local", "openai")
    assert by_alias["mine"]["key_configured"] is True
    assert by_alias["cloud"]["key_configured"] is False
    flat = repr(result.structured_content)
    assert "sk-secret" not in flat and "secret-host" not in flat


async def test_list_models_shows_derived_abilities_or_unknown(make_ctx):
    ctx = make_ctx(models={"known": {"model": "gemini/gemini-2.5-flash"},
                           "mine": {"model": "openai/some-local-model"}})
    async with Client(ImageServer(ctx).mcp) as client:
        result = await client.call_tool("list_models", {})
    by_alias = {m["alias"]: m for m in result.structured_content["models"]}
    assert by_alias["known"]["abilities"] == [
        "audio_input", "chat", "video_input", "vision"]
    assert by_alias["mine"]["abilities"] == "unknown"
    assert "capabilities" not in by_alias["mine"]


def test_a_known_wrong_model_warns_on_stderr_and_the_server_still_starts(
        make_ctx, tmp_path, monkeypatch, caplog, capsys):
    import logging

    config = tmp_path / "c.toml"
    config.write_text("[image]\ngen_model = 'gpt-4o'\nedit_model = 'openai/my-local'\n",
                      encoding="utf-8")
    started = []
    monkeypatch.setattr(ImageServer, "run", lambda self, **kw: started.append(True))
    monkeypatch.setattr("mymcps.core.context.LLMClient", lambda: make_ctx().llm)
    with caplog.at_level(logging.WARNING, logger="mymcps.core.server"):
        ImageServer.main(["--config", str(config)])
    assert started == [True]
    assert "gen_model" in caplog.text and "gpt-4o" in caplog.text
    assert "edit_model" not in caplog.text                 # unknown models are never warned about
    assert capsys.readouterr().out == ""


def test_old_settings_environment_variables_are_warned_about_and_ignored(
        tmp_path, monkeypatch, caplog, capsys):
    import logging

    config = tmp_path / "c.toml"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("MYMCPS_OUTPUT_DIR", "/somewhere")
    monkeypatch.setattr(ImageServer, "run", lambda self, **kw: None)
    with caplog.at_level(logging.WARNING, logger="mymcps.core.server"):
        ImageServer.main(["--config", str(config)])
    assert "MYMCPS_OUTPUT_DIR" in caplog.text and "Migrating" in caplog.text
    assert "/somewhere" not in caplog.text            # the name is shown, never the value
    assert capsys.readouterr().out == ""

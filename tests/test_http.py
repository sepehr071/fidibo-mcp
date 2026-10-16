import json
import re
from pathlib import Path

import httpx
import pytest

from fidibo_mcp import http

pytestmark = pytest.mark.anyio

BASE_LEVELS = "/flex/base-levels"


async def test_all_tools_are_read_only(client):
    tools = (await client.list_tools()).tools
    assert len(tools) == 11
    for t in tools:
        assert t.name.startswith("fd_"), t.name
        assert t.annotations.read_only_hint is True and t.annotations.destructive_hint is False, t.name
        assert t.description and t.title, t.name


async def test_readme_tool_tables_match_the_server(client):
    readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
    listed = re.findall(r"^\| `(fd_\w+)` \|", readme, re.M)
    assert sorted(listed) == sorted(t.name for t in (await client.list_tools()).tools)


async def test_dropped_connection_is_retried_once(client, api):
    attempts = []

    def flaky(request):
        attempts.append(request)
        if len(attempts) == 1:
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.", request=request)
        return httpx.Response(200, json={"data": {"result": []}})

    api[BASE_LEVELS] = flaky
    result = await client.call_tool("fd_categories", {})
    assert result.is_error and "Unknown level" in result.content[0].text  # reached the data on the 2nd attempt
    assert len(attempts) == 2


async def test_empty_200_body_is_retried_once(client, api):
    replies = iter([httpx.Response(200), httpx.Response(200, json={"data": {"result": []}})])
    api[BASE_LEVELS] = lambda r: next(replies)
    result = await client.call_tool("fd_categories", {})
    assert len(api.calls) == 2 and "Unknown level" in result.content[0].text


async def test_network_error_after_retry(client, api):
    def down(request):
        raise httpx.ConnectError("[SSL: UNEXPECTED_EOF_WHILE_READING]", request=request)

    api[BASE_LEVELS] = down
    result = await client.call_tool("fd_categories", {})
    assert result.is_error and "Could not reach fidibo.com (ConnectError)" in result.content[0].text
    assert len(api.calls) == 2


async def test_timeout_is_not_retried(client, api):
    def slow(request):
        raise httpx.ReadTimeout("timed out", request=request)

    api[BASE_LEVELS] = slow
    result = await client.call_tool("fd_categories", {})
    assert result.is_error and "did not answer in time" in result.content[0].text and len(api.calls) == 1


@pytest.mark.parametrize(
    ("status", "text"),
    [(404, "HTTP 404"), (429, "rate limiting"), (500, "server error (HTTP 500)"), (403, "refused"), (400, "rejected")],
)
async def test_http_errors_are_actionable(client, api, status, text):
    api[BASE_LEVELS] = lambda r: httpx.Response(status)
    result = await client.call_tool("fd_categories", {})
    assert result.is_error and text in result.content[0].text


async def test_non_json_reply(client, api):
    api[BASE_LEVELS] = lambda r: httpx.Response(200, text="<html>oops</html>")
    result = await client.call_tool("fd_categories", {})
    assert result.is_error and "non-JSON" in result.content[0].text


async def test_empty_page_204_is_an_empty_list(client, api):
    api["/flex/list/book"] = lambda r: httpx.Response(204)
    out = (await client.call_tool("fd_new", {})).structured_content
    assert out["count"] == 0 and out["books"] == [] and out["next_page"] is None


async def test_browser_user_agent_and_no_env_proxy(client, api, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")  # must be ignored (trust_env=False)
    api["/flex/list/book"] = {"data": {"result": []}}
    result = await client.call_tool("fd_new", {})
    assert not result.is_error and "Chrome" in api.calls[0].headers["User-Agent"]
    assert api.calls[0].method == "POST" and api.calls[0].url.host == "api.fidibo.com"


async def test_get_503_is_retried_once_but_post_is_not(client, api):
    replies = iter([httpx.Response(503), httpx.Response(200, json={"data": {"result": []}})])
    api[BASE_LEVELS] = lambda r: next(replies)
    result = await client.call_tool("fd_categories", {})
    assert len(api.calls) == 2 and "Unknown level" in result.content[0].text
    api["/flex/list/book"] = lambda r: httpx.Response(503)
    result = await client.call_tool("fd_new", {})
    assert result.is_error and len(api.calls) == 3


async def test_redirects_are_not_followed(client, api):
    api[BASE_LEVELS] = lambda r: httpx.Response(302, headers={"location": "https://evil.example/x"})
    result = await client.call_tool("fd_categories", {})
    assert result.is_error and len(api.calls) == 1


async def test_raw_client_one_text_block_no_structured_content_no_output_schema():
    from mcp import Client

    from fidibo_mcp.server import mcp

    http.set_transport(httpx.MockTransport(lambda r: httpx.Response(200, json={"data": {"result": []}})))
    async with Client(mcp) as raw:  # the `client` fixture patches call_tool; this one does not
        tools = (await raw.list_tools()).tools
        assert all(t.output_schema is None for t in tools)
        assert all('"title"' not in json.dumps(t.input_schema) for t in tools)
        result = await raw.call_tool("fd_new", {})
    assert len(result.content) == 1 and result.content[0].type == "text" and result.structured_content is None

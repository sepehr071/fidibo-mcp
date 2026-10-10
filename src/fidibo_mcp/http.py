"""Shared async HTTP client for the Fidibo API.

Fidibo serves everything from one JSON gateway, `https://api.fidibo.com` (book catalog under `/flex`).
No token, cookie or header is needed for public reads. Every tool goes through `api`. `_send` caps
concurrency, retries once when the server drops the connection or answers 200 with an empty body, and
turns HTTP failures into `ToolError` messages the model can act on. HTTP 204 (an empty page) returns `{}`.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError

API = "https://api.fidibo.com"
SITE = "https://fidibo.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0",
    "Accept": "application/json",
}

MAX_CONCURRENCY = 4

_transport: httpx.AsyncBaseTransport | None = None
_client: httpx.AsyncClient | None = None
_limit: asyncio.Semaphore | None = None


class ApiError(ToolError):
    """A failed upstream call."""


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Swap the transport (tests use httpx.MockTransport). Drops the current client."""
    global _transport, _client, _limit
    _transport, _client, _limit = transport, None, None


def _get_client() -> tuple[httpx.AsyncClient, asyncio.Semaphore]:
    global _client, _limit
    if _client is None:
        # Fidibo answers direct connections fine; a proxy is only used when the user opts in
        # with FIDIBO_MCP_PROXY.
        _client = httpx.AsyncClient(
            transport=_transport,
            headers=HEADERS,
            timeout=30,
            follow_redirects=True,
            trust_env=False,
            proxy=os.environ.get("FIDIBO_MCP_PROXY") or None,
        )
        _limit = asyncio.Semaphore(MAX_CONCURRENCY)
    assert _limit is not None
    return _client, _limit


async def api(path: str, params: dict[str, Any] | None = None, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET `path` (or POST the JSON `body`, used by the book list, which is a read-only query) and return the
    parsed JSON; `{}` for an empty page (HTTP 204)."""
    r = await _send(
        "POST" if body is not None else "GET",
        f"{API}{path}",
        params={k: v for k, v in (params or {}).items() if v is not None},
        json=body,
    )
    if r.status_code == 204 or not r.content:
        return {}
    try:
        data = r.json()
    except ValueError as e:
        raise ApiError(f"fidibo.com returned a non-JSON response for {path} (HTTP {r.status_code}).") from e
    return data if isinstance(data, dict) else {}


def result(data: dict[str, Any]) -> Any:
    """The `data.result` payload of a Fidibo reply (list of cards/components, or an object)."""
    return (data.get("data") or {}).get("result")


async def _send(method: str, url: str, **kwargs: Any) -> httpx.Response:
    client, limit = _get_client()
    for attempt in (1, 2):
        try:
            async with limit:
                r = await client.request(method, url, **kwargs)
        except httpx.TimeoutException as e:
            raise ApiError("fidibo.com did not answer in time. Try again in a moment.") from e
        except httpx.TransportError as e:
            if attempt == 2:
                raise ApiError(
                    f"Could not reach fidibo.com ({type(e).__name__}). Check the internet connection, "
                    "or set FIDIBO_MCP_PROXY."
                ) from e
            continue
        if r.status_code == 200 and not r.content and attempt == 1:  # a retry works
            continue
        break
    if r.status_code >= 400:
        raise ApiError(_status_message(r.status_code))
    return r


def _status_message(code: int) -> str:
    if code == 400:
        return "fidibo.com rejected the parameters (HTTP 400)."
    if code in (401, 403):
        return f"fidibo.com refused the request (HTTP {code}). Turn off VPN/proxy or set FIDIBO_MCP_PROXY."
    if code == 404:
        return "Not found on fidibo.com (HTTP 404). The book, author, publisher or category id may be wrong."
    if code == 429:
        return "fidibo.com is rate limiting requests (HTTP 429). Wait a minute before retrying."
    if code >= 500:
        return f"fidibo.com had a server error (HTTP {code}). Try again later."
    return f"fidibo.com rejected the request (HTTP {code})."

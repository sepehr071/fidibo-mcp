"""Shared async HTTP client for the Fidibo API.

Fidibo serves everything from one JSON gateway, `https://api.fidibo.com` (book catalog under `/flex`).
No token, cookie or header is needed for public reads, but the client presents itself as Chrome (TLS, HTTP/2 and
headers) so it looks like the web app. Every tool goes through `api`. `_send` caps concurrency, adds a small
jitter, retries (up to MAX_RETRIES, backed off) when the server drops the connection, times out, answers 200 with
an empty body, or 429/5xx on a GET, and turns HTTP failures into `ToolError` messages the model can act on.
HTTP 204 (an empty page) returns `{}`.
"""

from __future__ import annotations

import asyncio
import os
import random
import re
import time
from typing import Any

import httpx
from httpx_curl_cffi import AsyncCurlTransport
from mcp.server.mcpserver.exceptions import ToolError

API = "https://api.fidibo.com"
SITE = "https://fidibo.com"

HEADERS = {
    # User-Agent, sec-ch-ua and TLS come from the impersonated Chrome profile (see _get_client).
    "Accept": "application/json",
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
    "Origin": SITE,
    "Referer": f"{SITE}/",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "priority": "u=1, i",
}

MAX_CONCURRENCY = 2
JITTER = (0.15, 0.6)  # seconds before each upstream call
RETRY_DELAY = 0.5  # base of the exponential backoff, seconds
MAX_RETRIES = 2
MAX_RETRY_WAIT = 10  # cap for Retry-After and backoff, seconds

_transport: httpx.AsyncBaseTransport | None = None
_client: httpx.AsyncClient | None = None
_limit: asyncio.Semaphore | None = None
_proxy_index = 0
_retired: set[asyncio.Task] = set()
_browser_lock: asyncio.Lock | None = None
_cleared: tuple[httpx.AsyncClient, float] | None = None


class _XhrTransport(AsyncCurlTransport):
    """The Chrome profile sends navigation-only headers; a None value makes curl drop them (API calls are XHR)."""

    def _create_request_params(self, req: httpx.Request) -> dict[str, Any]:
        p = super()._create_request_params(req)
        p["headers"] = [*p["headers"], (b"upgrade-insecure-requests", None), (b"sec-fetch-user", None)]
        return p


class ApiError(ToolError):
    """A failed upstream call."""


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Swap the transport (tests use httpx.MockTransport). Drops the current client."""
    global _transport, _client, _limit, _proxy_index, _browser_lock, _cleared
    _transport, _client, _limit, _proxy_index, _browser_lock, _cleared = transport, None, None, 0, None, None


def _proxies() -> list[str]:
    """FIDIBO_MCP_PROXY: one proxy URL, or a comma-separated list used one at a time."""
    return [p.strip() for p in os.environ.get("FIDIBO_MCP_PROXY", "").split(",") if p.strip()]


# A bare HTML 403 is a normal CDN answer, not a bot check: only a known marker counts.
_CHALLENGE = re.compile(r"just a moment|captcha|challenge|arvan|attention required|enable javascript", re.I)


def _is_challenge(r: httpx.Response) -> bool:
    """A bot-check page: 403/429/503 with an HTML body that carries a known challenge marker."""
    return (
        r.status_code in (403, 429, 503)
        and "html" in r.headers.get("content-type", "") + r.text[:20].lower()
        and bool(_CHALLENGE.search(r.text[:5000]))
    )


def _next_proxy(client: httpx.AsyncClient) -> None:
    """Sticky pool: move to the next proxy after a block or connect error; the next call rebuilds the client.

    Only the client that failed may rotate: a slower request that failed on an old client must not skip a good proxy.
    The old client is closed late because other requests may still be using it.
    """
    global _client, _limit, _proxy_index
    if len(_proxies()) < 2 or client is not _client:
        return
    _client, _limit, _proxy_index = None, None, _proxy_index + 1
    t = asyncio.create_task(_close_later(client))
    _retired.add(t)
    t.add_done_callback(_retired.discard)


async def _close_later(client: httpx.AsyncClient) -> None:
    await asyncio.sleep(35)  # longer than the 30 s request timeout
    await client.aclose()


def _get_client() -> tuple[httpx.AsyncClient, asyncio.Semaphore]:
    global _client, _limit
    if _client is None:
        # Fidibo answers direct connections fine; a proxy is only used when the user opts in
        # with FIDIBO_MCP_PROXY. curl_cffi presents Chrome's TLS/HTTP2 fingerprint and default headers; the
        # proxy goes to the transport (a client-level proxy would be ignored once a transport is given).
        proxies = _proxies()
        _client = httpx.AsyncClient(
            transport=_transport
            or _XhrTransport(
                impersonate="chrome",
                default_headers=True,
                proxy=proxies[_proxy_index % len(proxies)] if proxies else None,
                max_connections=2 * MAX_CONCURRENCY,
            ),
            headers=HEADERS,
            timeout=30,
            limits=httpx.Limits(max_connections=2 * MAX_CONCURRENCY),
            follow_redirects=False,  # the API never redirects; do not follow one to another host
            trust_env=False,
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


async def _browser_cookies(proxy: str | None) -> list[dict[str, Any]]:
    """Open the home page in headless patchright, wait for the challenge to clear, return the cookies."""
    try:
        from patchright.async_api import async_playwright
    except ImportError as e:
        raise ApiError(
            "Fidibo served a bot-check page. Install the browser extra (`pip install fidibo-mcp[browser]`, or "
            "`uvx --with patchright==1.63.0 fidibo-mcp`) and run `patchright install chromium`."
        ) from e
    u = httpx.URL(proxy) if proxy else None
    opts = u and {"server": f"{u.scheme}://{u.host}:{u.port}", "username": u.username, "password": u.password}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, proxy=opts)
        try:
            page = await browser.new_page()
            await page.goto(SITE, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_function(
                "!/just a moment|access denied|attention required|arvancloud/i.test(document.title)", timeout=30_000
            )
            return await browser.contexts[0].cookies()
        finally:
            await browser.close()


async def _clear_challenge(client: httpx.AsyncClient) -> None:
    """Rung 2: let a real browser pass the bot check once and share its cookies with the httpx jar."""
    global _browser_lock, _cleared
    _browser_lock = _browser_lock or asyncio.Lock()
    async with _browser_lock:  # one browser at a time; callers that waited reuse the cookies just fetched
        if _cleared and _cleared[0] is client and time.monotonic() - _cleared[1] < 30:
            return
        proxies = _proxies()
        try:
            cookies = await _browser_cookies(proxies[_proxy_index % len(proxies)] if proxies else None)
        except ApiError:
            raise
        except Exception as e:
            raise ApiError(f"Fidibo bot check was not cleared by the browser ({type(e).__name__}).") from e
        for c in cookies:
            client.cookies.set(c["name"], c["value"], domain=c["domain"], path=c["path"])
        _cleared = (client, time.monotonic())


def _retry_after(r: httpx.Response) -> float | None:
    """Seconds from a numeric Retry-After on a 429/503, else None (HTTP-date form is ignored)."""
    v = r.headers.get("retry-after", "")
    return float(v) if r.status_code in (429, 503) and v.replace(".", "", 1).isdigit() else None


async def _once(client: httpx.AsyncClient, limit: asyncio.Semaphore, method: str, url: str, kwargs: Any):
    async with limit:
        await asyncio.sleep(random.uniform(*JITTER))
        return await client.request(method, url, **kwargs)


async def _send(method: str, url: str, **kwargs: Any) -> httpx.Response:
    for attempt in range(MAX_RETRIES + 1):
        last = attempt == MAX_RETRIES
        client, limit = _get_client()
        wait = None
        try:
            r = await _once(client, limit, method, url, kwargs)
            if _is_challenge(r):
                _next_proxy(client)
                client, limit = _get_client()
                await _clear_challenge(client)
                r = await _once(client, limit, method, url, kwargs)  # one retry; a second block is final
                if _is_challenge(r):
                    _next_proxy(client)
        except httpx.TimeoutException as e:
            if last:
                raise ApiError("fidibo.com did not answer in time. Try again in a moment.") from e
        except httpx.TransportError as e:
            if isinstance(e, httpx.ConnectError | httpx.ProxyError):
                _next_proxy(client)
            if last:
                raise ApiError(
                    f"Could not reach fidibo.com ({type(e).__name__}). Check the internet connection, "
                    "or set FIDIBO_MCP_PROXY."
                ) from e
        else:
            # an empty 200 and a GET 429/5xx are worth another try; a 403 never is
            if last or not (
                (r.status_code == 200 and not r.content)
                or (method == "GET" and (r.status_code == 429 or r.status_code >= 500))
            ):
                break
            wait = _retry_after(r)
        if wait is None:
            wait = RETRY_DELAY * 2**attempt * random.uniform(1, 1.5)
        await asyncio.sleep(min(wait, MAX_RETRY_WAIT))
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

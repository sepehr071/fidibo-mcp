# fidibo-mcp

Unofficial, read-only MCP server for Fidibo (fidibo.com), an Iranian store for ebooks and audiobooks (Digikala group).
Published: GitHub `sepehr071/fidibo-mcp`, PyPI `fidibo-mcp`, MCP Registry `io.github.sepehr071/fidibo-mcp`, listed in `../../iran-mcp`.
It is a sibling of `../shopino-mcp` and copies their layout and idioms; keep them in step.

API map this server is built on (endpoints, samples, quirks, test report): `../fidibo/`.

## Layout

- `src/fidibo_mcp/http.py`: the only HTTP code. One shared `httpx.AsyncClient` (`trust_env=False`) on a Chrome-impersonating
  `httpx_curl_cffi` transport (TLS, HTTP/2 and the User-Agent / sec-ch-ua headers come from the profile; `HEADERS` holds
  only the XHR headers the site sends). Proxy only from `FIDIBO_MCP_PROXY`, a comma-separated list used sticky: next
  proxy on a block (403/429/challenge) or connect error. A concurrency semaphore (`MAX_CONCURRENCY` 2) and a 150-600 ms
  random `JITTER` before each upstream call. `api(path, params, body=None)` for the JSON gateway
  `https://api.fidibo.com` (GET, or POST when `body` is given: the book list is a read-only POST query), `result()`
  for `data.result`. Up to `MAX_RETRIES` (2) retries with exponential backoff and jitter (base `RETRY_DELAY` 0.5 s, wait
  capped at 10 s, `Retry-After` honoured) on timeouts, dropped connections, an empty 200 body and 429/5xx on GETs; a 403
  is never retried. A bot-check page (`_is_challenge`) is cleared once by a headless patchright browser, only if
  `fidibo-mcp[browser]` is installed and `patchright install chromium` was run; otherwise `ApiError`. No redirects
  followed, HTTP 204 returns `{}`, `ApiError(ToolError)`, `set_transport()` for tests.
- `registry.py`: `@tool("Title")` collects tools. `server.py`: registers them with read-only annotations, holds `INSTRUCTIONS`.
- Tools: `books.py` (search, browse, bestsellers, new, free, categories; also `_card`, `_scan`, `book_list`),
  `detail.py` (book, reviews, similar), `people.py` (author, publisher). 11 tools, all `fd_*`.
- `tests/`: `test_<module>.py` unit tests (MockTransport + trimmed real fixtures in `tests/fixtures/`),
  `test_live_<module>.py` live tests (`@pytest.mark.live`), `test_http.py` for the client and the README tool tables.

## Commands

uv needs the local proxy to download packages; the server and tests call Fidibo directly (env proxies are ignored).

```bash
export HTTPS_PROXY=http://127.0.0.1:10898 HTTP_PROXY=http://127.0.0.1:10898
uv sync
uv run ruff check . && uv run ruff format --check .
uv run python -m pytest -q            # unit tests, offline (`uv run pytest` hits a uv trampoline error on Windows)
uv run python -m pytest -m live -q    # one live test per tool, about 10 s
```

## Rules for changes

- Read-only only. Never call login/OTP (`/identity/*`), basket / payment, library / shelves / favorites, review or
  rating writes, `/flex/search/click`, the Fidibo Plus plans flow, or any analytics beacon.
- Output units: prices in **Toman** (the API is Toman; nothing to convert; the site's Rial view is x10). Card:
  `final_price` = `campaign.discounted_price` or `price` (what the customer pays), `price` = before discount (omitted
  when equal to `final_price`), `discount_pct` int computed, `free` = no `price` key (price 0), `in_plus` =
  `badges.subscription`, `rating` absent when nobody voted. `_slim` drops default values after filtering: absent
  `discount_pct` / `free` / `in_plus` / `ratings_count` mean 0 / false, `available` appears only when false. `image` and
  `url` stay on every card. Default `limit` is 10; reviews are cut at 400 chars, book descriptions at 1500, publisher descriptions at 600 (`full_text=true` on
  fd_reviews / fd_book / fd_publisher skips the cut), reviewer names at 40.
- `fd_categories` caches `/flex/base-levels` in memory for an hour (`_levels`); `parent` filters one category. Category
  levels are checked against `LEVELS`; slugs from API data go into paths through `quote(slug, safe='')`.
- `_scan` fetches its (up to 3) pages with `asyncio.gather`, at least `SCAN_SIZE` (20) books per page when a filter is set; fd_author / fd_publisher fetch profile and books together.
- Descriptions are text from the site: INSTRUCTIONS tells the model to treat them as data. Tool input schemas have
  pydantic `title` keys stripped in `server.py` (`_untitled`).
- New tool: `@tool("Title")` async function, every param `Annotated[..., Field(...)]` with constraints and an example,
  docstring = what it returns + when to use + what to call next, compact dict output. Add a unit test with a real trimmed
  fixture, a live test, a README tool-table row, and an `INSTRUCTIONS` mention.
- Keep `README.md` tool tables equal to `list_tools()` (a unit test checks it). Deps stay `mcp`, `httpx`, `httpx-curl-cffi`, `curl-cffi`; the only extra is `browser` = `patchright==1.63.0`.
- Write ZWNJ as `\u200c` in code, never the invisible character.

## Fidibo quirks (keep them)

- No auth, token or header needed. `curl` gets an ArvanCloud 403 on fidibo.com pages (TLS fingerprint); the Chrome-impersonating
  client is fine, direct or through the proxy.
- Envelope `{data: {result, total, per_page}}`; many lists are UI components (`{component, items[]}`): search lists
  wrap cards in `result[0].items`, `POST /flex/list/book` returns cards directly in `result`. Empty page = HTTP 204.
- `POST /flex/list/book?page&limit` body keys: `order` (BESTSELLER, WEEK_BESTSELLER, MONTH_BESTSELLER, POPULAR, RECENT,
  LOWEST_PRICE, HIGHEST_PRICE), `contentType` [1,6] text / [2,7] audio, `categoryId` (numeric only; uuid or slug give an
  empty reply), `authorId`, `publisherId`, `excludeBookId`, `free`, `subscription_only` (`subscription` is ignored),
  `format`. No price-range filter anywhere: filter client-side (`_scan`, up to 3 pages). `total` is a constant 150.
- `GET /flex/search/list/content` takes `query, order, contentType "[1,6]", page, size`; ignores every price / Plus /
  free filter. `total` is the real count.
- Category slug to numeric id: `GET /flex/{ebooks|audiobooks}/categories/{slug}` -> `action.inputs[categoryId]`
  (same slug exists in both levels with different ids). Book `breadcrumb[].id` of `category_page` entries are the ids.
- `GET /flex/book/reviews/{slug}` needs the full slug; a bare id or `?bookId=` hangs until timeout. Same for
  `/flex/book/editions`. Do not call them.
- Sorting by price (both APIs) follows the price to pay; free books come first in cheapest order.
- No similar-books endpoint: `fd_similar` = bestsellers of the leaf category (parents as fallback).

## Release

Bump `version` in `pyproject.toml` and both versions in `server.json`, update `uv.lock` if deps changed, commit,
then `git tag vX.Y.Z && git push --tags`. `.github/workflows/publish.yml` tests, publishes to PyPI (trusted
publishing, environment `pypi`), creates the GitHub Release and publishes to the MCP Registry (GitHub OIDC).

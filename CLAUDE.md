# fidibo-mcp

Unofficial, read-only MCP server for Fidibo (fidibo.com), an Iranian store for ebooks and audiobooks (Digikala group).
Not published yet: no git repo, PyPI or MCP Registry release (planned: GitHub `sepehr071/fidibo-mcp`, PyPI `fidibo-mcp`).
It is a sibling of `../shopino-mcp` and copies their layout and idioms; keep them in step.

API map this server is built on (endpoints, samples, quirks, test report): `../fidibo/`.

## Layout

- `src/fidibo_mcp/http.py`: the only HTTP code. One shared `httpx.AsyncClient` (`trust_env=False`, proxy only from
  `FIDIBO_MCP_PROXY`), a concurrency semaphore, `api(path, params, body=None)` for the JSON gateway
  `https://api.fidibo.com` (GET, or POST when `body` is given: the book list is a read-only POST query), `result()`
  for `data.result`, one retry on dropped connections and on an empty 200 body, HTTP 204 returns `{}`,
  `ApiError(ToolError)`, `set_transport()` for tests.
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
uv run pytest -q            # unit tests, offline
uv run pytest -m live -q    # one live test per tool, about 10 s
```

## Rules for changes

- Read-only only. Never call login/OTP (`/identity/*`), basket / payment, library / shelves / favorites, review or
  rating writes, `/flex/search/click`, the Fidibo Plus plans flow, or any analytics beacon.
- Output units: prices in **Toman** (the API is Toman; nothing to convert; the site's Rial view is x10). Card:
  `final_price` = `campaign.discounted_price` or `price` (what the customer pays), `price` = before discount (set to
  `final_price` when there is no discount), `discount_pct` int computed, `free` = no `price` key (price 0), `in_plus` =
  `badges.subscription`, `rating` absent when nobody voted.
- New tool: `@tool("Title")` async function, every param `Annotated[..., Field(...)]` with constraints and an example,
  docstring = what it returns + when to use + what to call next, compact dict output. Add a unit test with a real trimmed
  fixture, a live test, a README tool-table row, and an `INSTRUCTIONS` mention.
- Keep `README.md` tool tables equal to `list_tools()` (a unit test checks it). Deps stay `mcp` + `httpx` only.
- Write ZWNJ as `\u200c` in code, never the invisible character.

## Fidibo quirks (keep them)

- No auth, token or header needed. `curl` gets an ArvanCloud 403 on fidibo.com pages (TLS fingerprint); httpx and
  requests are fine, direct or through the proxy.
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

## Release (when it is time)

Bump `version` in `pyproject.toml` and both versions in `server.json`, `git init`, create the GitHub repo, tag `vX.Y.Z`.
`.github/workflows/publish.yml` (copied from shopino-mcp, untested here) publishes to PyPI and the MCP Registry.

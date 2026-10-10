<!-- mcp-name: io.github.sepehr071/fidibo-mcp -->

# fidibo-mcp

**Let your AI agent search Persian ebooks and audiobooks on Fidibo, compare prices, and find free and Fidibo Plus books.**

Unofficial, read-only [MCP](https://modelcontextprotocol.io) server for [Fidibo](https://fidibo.com), the Iranian store
for ebooks and audiobooks (Digikala group). Search by title or author, see the price in Toman with discount, check
whether a book is free or in the Fidibo Plus subscription, read reviews, and browse bestsellers, new releases,
categories, authors and publishers, all from Claude, Cursor or Copilot. No account, no API key, nothing is bought or
changed.

## Quick start

You need [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
claude mcp add fidibo -- uvx fidibo-mcp
```

Any other MCP client: command `uvx`, args `["fidibo-mcp"]`.

## What it can do

- Search books and audiobooks by title, author or keyword; sort by price or date; filter by price range, free, Fidibo Plus
- Full record of a book: price and discount in **Toman**, format, pages or duration, narrators, rating with star distribution, Plus flag, description, printed price
- Reader reviews, similar books, an author's or publisher's books
- Bestsellers (week, month, all time), new releases, free books, any category

## Tools

All tools are read-only and start with `fd_`. Every book in a result is a compact card: `id`, `title`, `type` (ebook /
audiobook / microbook ...), `authors`, `publisher`, `final_price` (what you pay) and `price` (before discount) in Toman,
`discount_pct`, `free`, `in_plus`, `rating`, `url`.

### Find books

| Tool | What it does |
|---|---|
| `fd_search` | Search by title, author or keyword; `kind` ebook / audio; sort relevance, cheapest, most expensive, newest; price range, free and Plus filters |
| `fd_browse` | List books of a category (or everything) by bestseller, popular, newest or price; free / Plus / price filters |
| `fd_bestsellers` | Top sellers of the week, month or all time, per kind and category |
| `fd_new` | Newest books and audiobooks |
| `fd_free` | Free ebooks and audiobooks |
| `fd_categories` | Category and sub-category slugs of a top level (ebooks, audiobooks, education, magazines, podcasts) |

### One book, people

| Tool | What it does |
|---|---|
| `fd_book` | Full record: price, discount, pages or duration, size, narrators, rating distribution, Plus flag, description, printed price |
| `fd_reviews` | Reader reviews with stars, date and likes |
| `fd_similar` | Bestsellers of the book's category (Fidibo has no similar-books endpoint) |
| `fd_author` | An author's, translator's or narrator's profile and books (by id or name) |
| `fd_publisher` | A publisher's profile and books (by id or name) |

## Good to know

- **Prices are Toman.** The API returns Toman (checked against the site); `final_price` is the price to pay after a campaign discount, `price` is before it. Free books have price 0.
- `in_plus` means the book is in the Fidibo Plus subscription catalog; it still has a normal buy price.
- Price range, free and Plus filters of `fd_search` are applied after fetching (up to 3 pages per call); use `next_page` to continue. `fd_browse` filters free and Plus on the server and the price range after fetching.
- Fidibo lists are capped: the book list reports at most 150 matches, `fd_search` `total_matches` is the real count.
- Persian queries work best.

## Configuration

The server calls `api.fidibo.com` directly and ignores system proxy variables. To use a proxy set `FIDIBO_MCP_PROXY=http://host:port`.

## Development

```bash
export HTTPS_PROXY=http://127.0.0.1:10898 HTTP_PROXY=http://127.0.0.1:10898   # uv downloads only
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pytest -q            # offline, recorded fixtures
uv run pytest -m live -q    # real API, one test per tool
```

The API map this server is built on lives next to it in `../fidibo/`.

## Disclaimer

Unofficial; not affiliated with Fidibo or Digikala. Read-only access to the data of public pages. Keep request rates low.

## License

MIT

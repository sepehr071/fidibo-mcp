<!-- mcp-name: io.github.sepehr071/fidibo-mcp -->

# fidibo-mcp: Fidibo MCP server for AI agents

**Unofficial, read-only MCP server that lets your AI agent search Persian ebooks and audiobooks on Fidibo (فیدیبو), compare prices, and find free and Fidibo Plus books.**

An [MCP](https://modelcontextprotocol.io) server for [Fidibo](https://fidibo.com), the Iranian store
for ebooks and audiobooks (Digikala group). Search by title or author, see the price in Toman with discount, check
whether a book is free or in the Fidibo Plus subscription, read reviews, and browse bestsellers, new releases,
categories, authors and publishers, all from Claude, Cursor or Copilot. No account, no API key, nothing is bought or
changed.

[Quick start](#quick-start) · [Tools](#tools) · [FAQ](#faq) · [فارسی](#فارسی)

---

## For AI agents

- **What:** Unofficial MCP server for Fidibo (فیدیبو, fidibo.com), an Iranian ebook and audiobook store. Queries in Persian work best; prices in Toman.
- **Install:** `claude mcp add fidibo -- uvx fidibo-mcp` (stdio, needs [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.10+).
- **Auth:** none. Optional `FIDIBO_MCP_PROXY` sets an HTTP proxy (or a comma-separated list) for every request.
- **Access:** read-only. It cannot log in, buy, review or touch a library.
- **Tools:** 11, all prefixed `fd_`. Start with `fd_search`, `fd_book`, `fd_bestsellers`, `fd_free`, `fd_browse`.
- **Typical sequence:** `fd_search` -> `fd_book` -> `fd_reviews`; `fd_categories` -> `fd_browse` to list a category.
- **Use when:** the user wants to find a Persian ebook or audiobook on Fidibo, compare price and discount, check free or Fidibo Plus books, or list bestsellers and new releases.
- **Do not use when:** the user wants to buy or read a book, or needs the user's own library or orders.
- **Output:** compact JSON book cards. Prices in Toman (`final_price` is what you pay, `price` before discount), `in_plus` marks Fidibo Plus; pass `id` between tools and `next_page` to continue.
- **Machine-readable:** [server.json](https://github.com/sepehr071/fidibo-mcp/blob/main/server.json), and the catalog of all Iranian MCP servers [awesome-iran-mcp](https://github.com/sepehr071/awesome-iran-mcp) (`TOOLS.md`, `servers.json`, `llms.txt`).

## Quick start

You need [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
claude mcp add fidibo -- uvx fidibo-mcp
```

Any other MCP client: command `uvx`, args `["fidibo-mcp"]` (or `pip install fidibo-mcp` and run `fidibo-mcp`).

## What it can do

- Search books and audiobooks by title, author or keyword; sort by price or date; filter by price range, free, Fidibo Plus
- Full record of a book: price and discount in **Toman**, format, pages or duration, narrators, rating with star distribution, Plus flag, description, printed price
- Reader reviews, similar books, an author's or publisher's books
- Bestsellers (week, month, all time), new releases, free books, any category

## Tools

All tools are read-only and start with `fd_`. Every book in a result is a compact card: `id`, `title`, `type` (ebook /
audiobook / microbook ...), `authors`, `publisher`, `final_price` (what you pay) in Toman, `price` (before discount, only when discounted),
`discount_pct`, `free`, `in_plus` (each only when set), `rating`, `image`, `url`. Default page size is 10 books.

### Find books

| Tool | What it does |
|---|---|
| `fd_search` | Search by title, author or keyword; `kind` ebook / audio; sort relevance, cheapest, most expensive, newest; price range, free and Plus filters |
| `fd_browse` | List books of a category (or everything) by bestseller, popular, newest or price; free / Plus / price filters |
| `fd_bestsellers` | Top sellers of the week, month or all time, per kind and category |
| `fd_new` | Newest books and audiobooks |
| `fd_free` | Free ebooks and audiobooks |
| `fd_categories` | Category and sub-category slugs of a top level (ebooks, audiobooks, education, magazines, podcasts); `parent` narrows to one category |

### One book, people

| Tool | What it does |
|---|---|
| `fd_book` | Full record: price, discount, pages or duration, size, narrators, rating distribution, Plus flag, description, printed price |
| `fd_reviews` | Reader reviews with stars, date and likes |
| `fd_similar` | Bestsellers of the book's category (Fidibo has no similar-books endpoint) |
| `fd_author` | An author's, translator's or narrator's profile and books (by id or name) |
| `fd_publisher` | A publisher's profile and books (by id or name) |

## Good to know

- **Prices are Toman.** The API returns Toman (checked against the site); `final_price` is the price to pay after a campaign discount, `price` is before it (present only with a discount). Free books have price 0.
- `in_plus` means the book is in the Fidibo Plus subscription catalog; it still has a normal buy price.
- Price range, free and Plus filters of `fd_search` are applied after fetching (up to 3 pages per call); use `next_page` to continue. `fd_browse` filters free and Plus on the server and the price range after fetching.
- Fidibo lists are capped: the book list reports at most 150 matches, `fd_search` `total_matches` is the real count.
- Persian queries work best.

## FAQ

**Is there a Fidibo API or MCP server for AI agents?**
Yes: this unofficial MCP server wraps the public JSON API the Fidibo website itself uses, so Claude, Cursor or
Copilot can search books and read prices and reviews.

**Is it official, safe and free?**
It is unofficial, open source (MIT) and free. It is read-only, needs no account or API key, and runs on your
machine with no hosted server in between.

**Can it buy a book or manage my Fidibo Plus subscription?**
No. It only reads public catalog data. Buying, reading and subscriptions happen on fidibo.com or in the Fidibo app.

## Configuration

The server calls `api.fidibo.com` directly and ignores system proxy variables. Requests present as Chrome (TLS, HTTP/2 and headers), at most 2 at a time with a short random delay. To use a proxy set `FIDIBO_MCP_PROXY=http://host:port`; a comma-separated list is used one at a time, the next proxy taking over when one is blocked (403/429) or cannot connect. If Fidibo serves a bot-check page, install the browser extra (`pip install fidibo-mcp[browser]`) and run `patchright install chromium`.

## Development

```bash
export HTTPS_PROXY=http://127.0.0.1:10898 HTTP_PROXY=http://127.0.0.1:10898   # uv downloads only
uv sync
uv run ruff check . && uv run ruff format --check .
uv run python -m pytest -q            # offline, recorded fixtures
uv run python -m pytest -m live -q    # real API, one test per tool
```

The API map this server is built on lives next to it in `../fidibo/`.

<a id="فارسی"></a>

## فارسی: سرور MCP فیدیبو

<div dir="rtl">

**fidibo-mcp** یک سرور MCP غیررسمی برای فیدیبو است که به دستیار هوش مصنوعی شما (Claude، Cursor، Copilot و ...) اجازه
می&zwnj;دهد در میان کتاب&zwnj;های الکترونیکی و صوتی ایران جستجو کند، قیمت و تخفیف را ببیند، کتاب&zwnj;های رایگان و
فیدیبو پلاس را پیدا کند و پرفروش&zwnj;ها و تازه&zwnj;ها را فهرست کند.

- فقط خواندنی است و حساب کاربری یا کلید API نمی&zwnj;خواهد.
- همه قیمت&zwnj;ها به تومان است.

بپرسید: «کتاب&zwnj;های صوتی رایگان فیدیبو درباره تاریخ کدامند؟»

</div>

## Related servers

- [Taaghche MCP server](https://github.com/sepehr071/taaghche-mcp) for Iranian ebook and audiobook prices on Taaghche
- [30book MCP server](https://github.com/sepehr071/30book-mcp) for printed Iranian and foreign books
- All Iranian MCP servers: [awesome-iran-mcp](https://github.com/sepehr071/awesome-iran-mcp)

## Disclaimer

Unofficial; not affiliated with Fidibo or Digikala. Read-only access to the data of public pages. Keep request rates low.

If this saves you clicks, a star helps others find it.

## License

MIT

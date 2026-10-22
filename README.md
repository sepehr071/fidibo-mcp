<!-- mcp-name: io.github.sepehr071/fidibo-mcp -->

# fidibo-mcp: Fidibo MCP server for AI agents

**Let your AI agent shop for Persian ebooks and audiobooks on Fidibo (فیدیبو).**<br>
An unofficial, read-only MCP server for [Fidibo](https://fidibo.com), the Iranian ebook and audiobook store from the Digikala group: search by title or author, compare prices in Toman, find free and Fidibo Plus books, read reviews, and browse bestsellers, new releases, authors and publishers.<br>
Works with Claude, Cursor, Copilot and any other [MCP](https://modelcontextprotocol.io) client. No account, no API key.

[![PyPI](https://img.shields.io/pypi/v/fidibo-mcp?color=2563eb)](https://pypi.org/project/fidibo-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/fidibo-mcp)](https://pypi.org/project/fidibo-mcp/)
[![CI](https://github.com/sepehr071/fidibo-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/sepehr071/fidibo-mcp/actions/workflows/ci.yml)
[![MCP Registry](https://img.shields.io/badge/MCP_Registry-io.github.sepehr071%2Ffidibo--mcp-7c3aed)](https://registry.modelcontextprotocol.io/?q=fidibo-mcp)
[![License: MIT](https://img.shields.io/badge/license-MIT-16a34a)](https://github.com/sepehr071/fidibo-mcp/blob/main/LICENSE)
[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_fidibo--mcp-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](https://vscode.dev/redirect/mcp/install?name=fidibo&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22fidibo-mcp%22%5D%7D)

[For AI agents](#for-ai-agents) · [Why](#why) · [What it can do](#what-it-can-do) · [Quick start](#quick-start) · [Tools](#tools) · [How it works](#how-it-works) · [Good to know](#good-to-know) · [FAQ](#faq) · [Configuration](#configuration) · [فارسی](#فارسی) · [Development](#development)

---

## For AI agents

- **What:** unofficial MCP server for Fidibo (فیدیبو, fidibo.com), an Iranian store for ebooks, audiobooks, microbooks and magazines. Queries in Persian work best; prices in Toman.
- **Install:** `uvx fidibo-mcp` or `claude mcp add fidibo -- uvx fidibo-mcp`. Transport: stdio. Needs [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python 3.10+).
- **Auth:** none, no API key or account. Optional `FIDIBO_MCP_PROXY` (HTTP proxy, or a comma-separated list).
- **Access:** read-only. It cannot log in, buy, add to a library, rate or review, so no confirmation is needed before calling any tool.
- **Tools:** 11, all prefixed `fd_`. Start with `fd_search`, `fd_book`, `fd_bestsellers`, `fd_free`, `fd_browse`.
  Typical sequence: `fd_search` -> `fd_book` -> `fd_reviews`; `fd_categories` -> `fd_browse` to list a category.
- **Units:** prices in Toman (`final_price` is what the customer pays, `price` is before discount and appears only when discounted). Ratings 0-5, review stars 1-5.
- **Use when:** the user wants to find a Persian or translated ebook or audiobook on Fidibo, compare price and discount, check free or Fidibo Plus books, read reviews, or list bestsellers and new releases.
- **Do not use when:** the user wants to buy or read a book, or needs their own library, orders or subscription status.
- **Output:** compact JSON book cards. Pass the book `id` between tools and `next_page` back as `page` to continue a list.
- **Machine-readable:** [`server.json`](https://github.com/sepehr071/fidibo-mcp/blob/main/server.json) and the
  [awesome-iran-mcp catalog](https://github.com/sepehr071/awesome-iran-mcp) (`TOOLS.md`, `servers.json`, `llms.txt`).

## Why

Fidibo sells the same title as an ebook, an audiobook and sometimes a microbook, with campaign discounts, a free section and a separate Fidibo Plus subscription catalog. Answering "is this audiobook free, or at least on sale, and is it any good?" means opening several pages. An agent with `fidibo-mcp` does it in a few calls: `fd_search`, then `fd_book`, then `fd_reviews`.

## What it can do

- Search books and audiobooks by title, author or keyword; sort by price or date; filter by price range, free and Fidibo Plus
- Full record of a book: price and discount in **Toman**, format, pages or duration, narrators, rating with star distribution, Plus flag, description, printed price
- Reader reviews, similar books, an author's, translator's or narrator's books, a publisher's books
- Bestsellers (week, month, all time), new releases, free books, any category
- Read-only by design: no login, no purchase, no library or review writes

Example prompts:

- "Find the cheapest audiobook of The Little Prince on Fidibo and tell me if it is free with Fidibo Plus."
- "What are this month's bestselling ebooks in the history category, with prices?"
- "Show me free audiobooks on Fidibo, and read the reviews of the first one."
- <span dir="rtl">کتاب&zwnj;های صوتی رایگان فیدیبو درباره تاریخ کدامند؟</span>
- <span dir="rtl">پرفروش&zwnj;ترین کتاب&zwnj;های این هفته در فیدیبو را با قیمت فهرست کن.</span>
- <span dir="rtl">آثار این نویسنده در فیدیبو چه قیمتی دارند و کدام تخفیف دارند؟</span>

## Quick start

You need [uv](https://docs.astral.sh/uv/getting-started/installation/). No API key or account.

<details open>
<summary><b>Claude Code</b></summary>

```bash
claude mcp add fidibo -- uvx fidibo-mcp
```
</details>

<details>
<summary><b>Claude Desktop</b></summary>

Settings → Developer → Edit Config, then add:

```json
{
  "mcpServers": {
    "fidibo": { "command": "uvx", "args": ["fidibo-mcp"] }
  }
}
```
</details>

<details>
<summary><b>Cursor</b></summary>

Add the Claude Desktop block to `~/.cursor/mcp.json`.
</details>

<details>
<summary><b>VS Code (Copilot agent mode)</b></summary>

Click **Install in VS Code** above, or add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "fidibo": { "type": "stdio", "command": "uvx", "args": ["fidibo-mcp"] }
  }
}
```
</details>

<details>
<summary><b>Codex CLI</b></summary>

```bash
codex mcp add fidibo -- uvx fidibo-mcp
```

Or in `~/.codex/config.toml`:

```toml
[mcp_servers.fidibo]
command = "uvx"
args = ["fidibo-mcp"]
```
</details>

<details>
<summary><b>Gemini CLI</b></summary>

Add to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "fidibo": { "command": "uvx", "args": ["fidibo-mcp"] }
  }
}
```
</details>

<details>
<summary><b>Windsurf</b></summary>

Add the Claude Desktop block to `~/.codeium/windsurf/mcp_config.json`.
</details>

<details>
<summary><b>Anything else</b></summary>

It is a standard stdio MCP server: run `uvx fidibo-mcp`, or `pip install fidibo-mcp` and run `fidibo-mcp`.
</details>

## Tools

All 11 tools are read-only (annotated `readOnlyHint: true`) and start with `fd_`. Every book in a result is a compact card: `id`, `title`, `type` (ebook / audiobook / microbook / micro_audiobook / magazine), `authors`, `publisher`, `final_price` (what you pay) in Toman, `price` (before discount, only when discounted), `discount_pct`, `free`, `in_plus` (each only when set), `rating`, `image`, `url`. Default page size is 10 books.

### Find books

| Tool | What it does |
|---|---|
| `fd_search` | Search ebooks and audiobooks by title, author or keyword; cards with price (Toman), rating, authors |
| `fd_browse` | List books of a category (or all) in a chosen order, with free / Plus / price filters |
| `fd_bestsellers` | Top sellers of the week, month or all time, per kind and category (Toman) |
| `fd_new` | Newest books and audiobooks, per kind and category (Toman) |
| `fd_free` | Free ebooks and audiobooks (price 0), per kind and category |
| `fd_categories` | List category and sub-category slugs (with Persian titles) of one top level |

### One book, people

| Tool | What it does |
|---|---|
| `fd_book` | One book's full record: price (Toman), format, pages or duration, size, people, rating and star distribution |
| `fd_reviews` | Reader reviews of a book: text, 1-5 stars, date, likes, replies, total count |
| `fd_similar` | Books like this one: bestsellers of its category, the book itself left out (Toman) |
| `fd_author` | An author's, translator's or narrator's profile and books (Toman) |
| `fd_publisher` | A publisher's profile and books (Toman) |

## How it works

```text
  AI agent  (Claude, Cursor, Copilot, ...)
      │
      │  MCP over stdio
      ▼
  fidibo-mcp  (runs on your machine)
      │
      │  HTTPS
      └──────▶  api.fidibo.com   books, prices, reviews, authors, publishers
```

`fidibo-mcp` runs locally and calls the same JSON API the fidibo.com website uses. There is no hosted server in between and no API key. Requests present as Chrome (TLS, HTTP/2 and headers), at most 2 at a time with a short random delay; timeouts, dropped connections and 429/5xx answers are retried up to twice with backoff.

## Good to know

- **Prices are Toman.** The API returns Toman (the site's Rial view is x10); nothing is converted. `final_price` is the price to pay after a campaign discount, `price` is before it (present only with a discount). Free books have price 0 and `free: true`.
- **Absent flags mean false or 0:** `free`, `in_plus`, `discount_pct`, `ratings_count`. `available` appears only when false. `rating` is absent when nobody voted.
- `in_plus` means the book is in the Fidibo Plus subscription catalog; it still has a normal buy price.
- **Filters are applied after fetching.** The price range, free and Plus filters of `fd_search` (and the price range of the other lists) look at up to 3 pages per call; a narrow filter may need more pages, so pass `next_page` back as `page`. `fd_browse` filters free and Plus on the server.
- **List totals are capped:** the book list reports at most 150 matches; `fd_search` `total_matches` is the real count.
- **Text is cut by default:** reviews at 400 characters, book descriptions at 1500, publisher descriptions at 600. Pass `full_text=true` to `fd_reviews`, `fd_book` or `fd_publisher` for the full text.
- **No similar-books endpoint:** `fd_similar` returns bestsellers of the book's category.
- **Persian queries work best** (`شازده کوچولو`).
- **Does not do:** log in, buy, read a book, touch a library, shelves, favorites, reviews or ratings, or manage a Fidibo Plus subscription.
- Review, description and name text comes from the site and is treated as data, not instructions.
- **Proxy:** `FIDIBO_MCP_PROXY` (see [Configuration](#configuration)). System proxy variables are ignored on purpose.

## FAQ

<details>
<summary><b>Is there a Fidibo API or MCP server for AI agents?</b></summary>

Yes: `fidibo-mcp` is an unofficial MCP server with 11 read-only tools. It calls the same public JSON API the Fidibo website uses, so Claude, Cursor or Copilot can search books and read prices and reviews. No API key is needed.
</details>

<details>
<summary><b>How do I use Fidibo with Claude, Cursor or Copilot?</b></summary>

Add the server with `claude mcp add fidibo -- uvx fidibo-mcp` (or the matching config in [Quick start](#quick-start)), then ask in plain language, in Persian or English.
</details>

<details>
<summary><b>Is it official, safe and free?</b></summary>

It is unofficial and not affiliated with Fidibo or Digikala. It is open source (MIT), free, and read-only. It needs no account or API key and runs on your machine with no hosted server in between.
</details>

<details>
<summary><b>Can it buy a book or manage my Fidibo Plus subscription?</b></summary>

No. It only reads public catalog data. Buying, reading and subscriptions happen on fidibo.com or in the Fidibo app.
</details>

<details>
<summary><b>Are the prices in Toman or Rial?</b></summary>

Toman. The API answers in Toman, so nothing is converted; the site's Rial view is ten times larger.
</details>

<details>
<summary><b>How do I find free books or books in Fidibo Plus?</b></summary>

Use `fd_free` for free ebooks and audiobooks. `fd_search` and `fd_browse` have free and Plus filters; cards carry `free` and `in_plus` flags. A Plus book still has a normal buy price.
</details>

<details>
<summary><b>Do I need an Iranian IP?</b></summary>

Not in the author's testing: the Chrome-impersonating client works direct or through a proxy. If requests are blocked (403/429), set `FIDIBO_MCP_PROXY`. Normal system proxy variables are ignored on purpose.
</details>

<details>
<summary><b>Fidibo shows a bot-check page. What now?</b></summary>

Install the optional browser fallback (`pip install fidibo-mcp[browser]`), then run `patchright install chromium`. The server uses it once to clear the check.
</details>

<details>
<summary><b>How do I debug what the agent sees?</b></summary>

```bash
npx @modelcontextprotocol/inspector uvx fidibo-mcp
```
</details>

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `FIDIBO_MCP_PROXY` | unset | Optional HTTP proxy URL for every request, e.g. `http://host:port`. A comma-separated list is used one at a time: the next proxy takes over when one is blocked (403/429) or cannot connect. System proxy settings are ignored |

<a id="فارسی"></a>

## فارسی: سرور MCP فیدیبو

<div dir="rtl">

**fidibo-mcp** یک سرور MCP غیررسمی و فقط&zwnj;خواندنی برای فیدیبو، فروشگاه کتاب الکترونیکی و کتاب صوتی ایران (از گروه دیجی&zwnj;کالا)، است. این سرور به دستیار هوش مصنوعی شما (Claude، Cursor، Copilot و ...) اجازه می&zwnj;دهد در میان کتاب&zwnj;های الکترونیکی و صوتی فیدیبو جستجو کند، قیمت و تخفیف را ببیند، کتاب&zwnj;های رایگان و فیدیبو پلاس را پیدا کند، نظر خوانندگان را بخواند و پرفروش&zwnj;ها و تازه&zwnj;ها را فهرست کند.

**چه کارهایی می&zwnj;کند**

- جستجوی کتاب و کتاب صوتی با عنوان، نویسنده یا کلیدواژه، با فیلتر قیمت، رایگان و فیدیبو پلاس.
- اطلاعات کامل کتاب: قیمت و تخفیف به تومان، تعداد صفحه یا مدت زمان، گوینده، امتیاز و توضیحات.
- نظرات خوانندگان، کتاب&zwnj;های مشابه، کتاب&zwnj;های هر نویسنده، مترجم، گوینده و ناشر.
- پرفروش&zwnj;های هفته و ماه، تازه&zwnj;ها، کتاب&zwnj;های رایگان و هر دسته&zwnj;بندی.

**نکته&zwnj;ها**

- فقط خواندنی است: وارد حساب نمی&zwnj;شود، خرید نمی&zwnj;کند و کتابخانه یا اشتراک شما را تغییر نمی&zwnj;دهد.
- همه قیمت&zwnj;ها به تومان است.
- روی سیستم خود شما اجرا می&zwnj;شود و کلید API یا حساب کاربری نمی&zwnj;خواهد.
- جستجوی فارسی بهترین نتیجه را می&zwnj;دهد.

**نصب** (اول [uv](https://docs.astral.sh/uv/getting-started/installation/) را نصب کنید). در Claude Code:

</div>

```bash
claude mcp add fidibo -- uvx fidibo-mcp
```

<div dir="rtl">

در Claude Desktop، Cursor و بقیه برنامه&zwnj;ها همان تنظیم بخش [Quick start](#quick-start) را بگذارید.

**نمونه پرسش&zwnj;ها**

- «کتاب&zwnj;های صوتی رایگان فیدیبو درباره تاریخ کدامند؟»
- «پرفروش&zwnj;ترین کتاب&zwnj;های این ماه فیدیبو را با قیمت بگو.»
- «قیمت کتاب شازده کوچولو در فیدیبو چقدر است و تخفیف دارد؟»
- «کتاب&zwnj;های فیدیبو پلاس در دسته داستان کدامند؟»

**جستجوهای مرتبط:** فیدیبو، کتاب الکترونیکی، کتاب صوتی، کتاب رایگان، فیدیبو پلاس، قیمت کتاب، پرفروش&zwnj;ترین کتاب&zwnj;ها، نظر کاربران درباره کتاب.

</div>

## Development

```bash
git clone https://github.com/sepehr071/fidibo-mcp && cd fidibo-mcp
uv sync
uv run python -m pytest -q            # offline, recorded fixtures
uv run python -m pytest -m live -q    # real API, one test per tool
uv run ruff check .
```

Tools live in `src/fidibo_mcp/books.py`, `detail.py` and `people.py`; each is a typed async function with a docstring that tells the agent when to use it. Issues and PRs are welcome.

Releases: bump the version in `pyproject.toml` and `server.json`, then push a `v*` tag. GitHub Actions tests, publishes to PyPI and the [MCP Registry](https://registry.modelcontextprotocol.io), and creates the GitHub Release.

## Related servers

- [Taaghche MCP server](https://github.com/sepehr071/taaghche-mcp) for Iranian ebook and audiobook prices on Taaghche
- [30book MCP server](https://github.com/sepehr071/30book-mcp) for printed Iranian and foreign books
- [Digikala MCP server](https://github.com/sepehr071/digikala-mcp) for Iran's largest online store
- [Shopino MCP server](https://github.com/sepehr071/shopino-mcp)
- [awesome-iran-mcp](https://github.com/sepehr071/awesome-iran-mcp): catalog of all Iranian-service MCP servers

## Disclaimer

Unofficial and not affiliated with or endorsed by Fidibo or Digikala. Read-only access to the data of public pages, through the endpoints the fidibo.com web app uses, which can change without notice. Please keep request rates reasonable.

## License

[MIT](https://github.com/sepehr071/fidibo-mcp/blob/main/LICENSE)

If this saves you clicks, a star helps others find it.

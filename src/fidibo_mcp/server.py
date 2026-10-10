"""MCP server entry point: registers every read-only Fidibo tool."""

import logging

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from . import __version__, books, detail, people  # noqa: F401  (imports register the tools)
from .registry import TOOLS

INSTRUCTIONS = """\
Unofficial, read-only access to Fidibo (fidibo.com), an Iranian store for Persian and translated ebooks
(epub, pdf), audiobooks (mp3), microbooks and magazines, part of the Digikala group. Nothing here can log in,
buy, add to a library, rate or review.

Workflow:
1. Find a book: fd_search (title / author / keyword; kind ebook or audio; sort; price range, free, Plus filters).
2. Browse lists: fd_bestsellers (week / month / all time), fd_new, fd_free, or fd_browse (any order, category,
   free / Plus / price filters). Category slugs: fd_categories.
3. One book: fd_book (price, format, pages or duration, narrators, rating and star distribution, Plus flag,
   description, printed price), fd_reviews (reader reviews), fd_similar (same category).
4. People and publishers: fd_author (author, translator or narrator by id or name), fd_publisher.

Conventions: all prices are Toman (the API itself is Toman; the site's optional Rial view is just x10).
final_price is what the customer pays, price is before discount (equal when there is none), discount_pct is
an int. free = true means price 0. in_plus = the book is in the Fidibo Plus subscription catalog (readable with
the plan; it still has a normal buy price). rating is 0-5 (absent = no votes). type is ebook, audiobook,
microbook, micro_audiobook or magazine. Ids are numeric book ids; `url` is the web page. Persian queries work
best ('شازده کوچولو', 'رمان پلیسی'). Price range, free and Plus filters in fd_search are applied after
fetching, so a narrow filter may need several pages (use next_page).
"""

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True)

mcp = MCPServer(
    "fidibo-mcp",
    title="Fidibo",
    instructions=INSTRUCTIONS,
    version=__version__,
    website_url="https://github.com/sepehr071/fidibo-mcp",
)

for fn, title in TOOLS:
    mcp.add_tool(fn, title=title, annotations=READ_ONLY)


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per request floods client logs
    mcp.run()


if __name__ == "__main__":
    main()

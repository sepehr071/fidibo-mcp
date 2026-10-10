"""Finding books: search, browse a category / author / publisher list, bestsellers, new releases, free books, categories."""

from __future__ import annotations

import html
import re
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal

from pydantic import Field

from .http import SITE, ApiError, api, result
from .registry import tool

Kind = Annotated[
    Literal["any", "ebook", "audio"],
    Field(description="ebook = text books (epub/pdf, incl. microbooks), audio = audiobooks (mp3), any = both."),
]
Category = Annotated[
    str | None,
    Field(
        pattern=r"^[a-z0-9-]{2,80}(/[a-z0-9-]{2,80})?$",
        description="Category slug from fd_categories, e.g. 'story-foreign-drama' or 'psychology'. Audiobook categories: "
        "'audiobooks/story-foreign' (the level is taken from `kind` when omitted). Includes sub-categories.",
    ),
]
MinPrice = Annotated[int | None, Field(ge=0, description="Minimum price to pay in Toman, e.g. 20000.")]
MaxPrice = Annotated[int | None, Field(ge=1, description="Maximum price to pay in Toman, e.g. 100000.")]
Limit = Annotated[int, Field(ge=1, le=30, description="Books per page.")]
Page = Annotated[int, Field(ge=1, le=200, description="Page number, from 1 (use next_page of the previous reply).")]

# search/list content types: text = ebook + microbook, audio = audiobook + micro audiobook.
CONTENT_TYPES: dict[str, list[int] | None] = {"any": None, "ebook": [1, 6], "audio": [2, 7]}
SEARCH_SORTS = {
    "relevance": "RELEVANT",
    "cheapest": "LOWEST_PRICE",
    "most_expensive": "HIGHEST_PRICE",
    "newest": "RECENT",
}
LIST_SORTS = {
    "bestseller": "BESTSELLER",
    "week_bestseller": "WEEK_BESTSELLER",
    "month_bestseller": "MONTH_BESTSELLER",
    "popular": "POPULAR",
    "newest": "RECENT",
    "cheapest": "LOWEST_PRICE",
    "most_expensive": "HIGHEST_PRICE",
}
MAX_SCAN = 3  # pages fetched per call when a client-side filter is set

_TAG = re.compile(r"<[^>]*>|<[^>]*$")
_category_ids: dict[str, int] = {}


def _text(s: Any) -> str:
    """Plain text of an API string (search cards wrap matches in <b>, descriptions are HTML)."""
    return re.sub(r"[ \t]+", " ", html.unescape(_TAG.sub("", str(s or "")))).strip()


def _names(people: Any) -> str | None:
    names = [p.get("full_name") or p.get("name") for p in people or [] if isinstance(p, dict)]
    return "، ".join(n for n in names if n) or None


def _slug(c: dict[str, Any]) -> str | None:
    if c.get("slug"):
        return c["slug"]
    for i in (c.get("action") or {}).get("inputs") or []:
        if i.get("key") == "slug":
            return i.get("value")
    return None


def _prices(c: dict[str, Any]) -> tuple[int, int, int, bool]:
    """(price, final_price, discount_pct, free) in Toman. A free book has no `price` key."""
    price = int(c.get("price") or 0)
    discounted = (c.get("campaign") or {}).get("discounted_price")
    final = int(discounted) if discounted is not None else price
    pct = round(100 * (price - final) / price) if price and final < price else 0
    return price, final, pct, price == 0


def _card(c: dict[str, Any]) -> dict[str, Any]:
    """One book as a compact dict, from a search card, a list card or a book-item record."""
    price, final, pct, free = _prices(c)
    slug = _slug(c)
    rate = c.get("rate") or {}
    publisher = (c.get("publishers") or [{}])[0].get("name") or c.get("footerText")
    out = {
        "id": c["id"],
        "title": _text(c.get("title")),
        "type": c.get("content_type"),
        "file_format": c.get("format"),
        "authors": _names(c.get("authors")) or _text(c.get("subtitle")) or None,
        "translators": _names(c.get("translators")),
        "narrators": _names(c.get("narrators")),
        "publisher": publisher,
        "duration": c.get("time"),
        "final_price": final,
        "price": price if price else final,
        "discount_pct": pct,
        "free": free,
        "in_plus": bool((c.get("badges") or {}).get("subscription")),
        "available": c.get("status", "published") == "published",
        "rating": rate.get("score") if rate.get("responses") else None,
        "ratings_count": rate.get("responses") or 0,
        "image": (c.get("cover") or {}).get("image"),
        "url": f"{SITE}/book/{slug or c['id']}",
    }
    return {k: v for k, v in out.items() if v is not None}


def _keep(card: dict[str, Any], min_price: int | None, max_price: int | None, free: bool, plus: bool) -> bool:
    if free and not card["free"] or plus and not card["in_plus"]:
        return False
    if min_price is not None and card["final_price"] < min_price:
        return False
    return max_price is None or card["final_price"] <= max_price


def _check_range(min_price: int | None, max_price: int | None) -> None:
    if min_price is not None and max_price is not None and min_price > max_price:
        raise ApiError("min_price is higher than max_price.")


async def _scan(
    fetch: Callable[[int], Awaitable[tuple[list[dict[str, Any]], int | None]]],
    *,
    page: int,
    limit: int,
    min_price: int | None = None,
    max_price: int | None = None,
    free: bool = False,
    plus: bool = False,
) -> dict[str, Any]:
    """Fetch one page (or up to MAX_SCAN pages when a client-side filter is set) and build the reply."""
    filtered = min_price is not None or max_price is not None or free or plus
    books: list[dict[str, Any]] = []
    total = None
    scanned = 0
    next_page: int | None = None
    for n in range(page, page + (MAX_SCAN if filtered else 1)):
        raw, total = await fetch(n)
        scanned += 1
        books += [c for c in map(_card, raw) if _keep(c, min_price, max_price, free, plus)]
        next_page = n + 1 if len(raw) >= limit else None
        if next_page is None:
            break
    out: dict[str, Any] = {"count": len(books), "books": books, "next_page": next_page}
    if total is not None:
        out["total_matches"] = total
    if filtered:
        out["note"] = f"Price / free / Plus filters are applied after fetching ({scanned} page(s) scanned)."
    return out


@tool("Search books")
async def fd_search(
    query: Annotated[
        str,
        Field(
            min_length=2,
            max_length=100,
            description="Title, author or keyword, Persian works best, e.g. 'شازده کوچولو'.",
        ),
    ],
    kind: Kind = "any",
    sort: Annotated[
        Literal["relevance", "cheapest", "most_expensive", "newest"],
        Field(description="relevance (Fidibo's ranking), cheapest / most_expensive (price to pay), newest."),
    ] = "relevance",
    free_only: Annotated[bool, Field(description="Only free books (filtered after fetching).")] = False,
    plus_only: Annotated[
        bool, Field(description="Only books included in the Fidibo Plus subscription (filtered after fetching).")
    ] = False,
    min_price: MinPrice = None,
    max_price: MaxPrice = None,
    page: Page = 1,
    limit: Limit = 20,
) -> dict[str, Any]:
    """Search Fidibo's ebooks and audiobooks by title, author or keyword: price in Toman, discount, free and
    Fidibo Plus flags, rating, authors and publisher.

    Use first for "find the book X" / "is X on Fidibo and how much". kind='audio' for audiobooks only.
    Price range, free and Plus filters are applied after fetching (up to 3 pages per call); more results:
    pass next_page back as page. Full record of one book: fd_book. Reviews: fd_reviews.
    """
    _check_range(min_price, max_price)
    params: dict[str, Any] = {"query": query, "order": SEARCH_SORTS[sort], "size": limit}
    if types := CONTENT_TYPES[kind]:
        params["contentType"] = "[" + ",".join(map(str, types)) + "]"

    async def fetch(n: int) -> tuple[list[dict[str, Any]], int | None]:
        data = await api("/flex/search/list/content", {**params, "page": n})
        rows = result(data) or []
        return [i for c in rows for i in c.get("items") or []], (data.get("data") or {}).get("total")

    return await _scan(
        fetch, page=page, limit=limit, min_price=min_price, max_price=max_price, free=free_only, plus=plus_only
    )


async def _category_id(category: str, kind: str) -> int:
    level, _, slug = category.rpartition("/")
    level = level or ("audiobooks" if kind == "audio" else "ebooks")
    key = f"{level}/{slug}"
    if key not in _category_ids:
        data = await api(f"/flex/{level}/categories/{slug}")
        inputs = ((result(data) or {}).get("action") or {}).get("inputs") or []
        found = next((i["value"] for i in inputs if i.get("key") == "categoryId"), None)
        if found is None:
            raise ApiError(f"Category '{key}' not found. List slugs with fd_categories.")
        _category_ids[key] = int(found)
    return _category_ids[key]


async def book_list(
    *,
    sort: str,
    kind: str = "any",
    category: str | None = None,
    author_id: int | None = None,
    publisher_id: int | None = None,
    free: bool = False,
    plus: bool = False,
    exclude_id: int | None = None,
    category_id: int | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    page: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    """The universal book list (POST /flex/list/book, a read-only query) with optional client-side filters."""
    _check_range(min_price, max_price)
    body: dict[str, Any] = {"order": LIST_SORTS[sort]}
    if types := CONTENT_TYPES[kind]:
        body["contentType"] = types
    if category:
        category_id = await _category_id(category, kind)
    if category_id:
        body["categoryId"] = [category_id]
    if author_id:
        body["authorId"] = [author_id]
    if publisher_id:
        body["publisherId"] = [publisher_id]
    if exclude_id:
        body["excludeBookId"] = [exclude_id]
    if free:
        body["free"] = True
    if plus:
        body["subscription_only"] = True

    async def fetch(n: int) -> tuple[list[dict[str, Any]], int | None]:
        data = await api("/flex/list/book", {"page": n, "limit": limit}, body=body)
        return result(data) or [], None

    # free / plus are server-side here; only the price range is filtered after fetching.
    return await _scan(fetch, page=page, limit=limit, min_price=min_price, max_price=max_price)


@tool("Browse book lists")
async def fd_browse(
    sort: Annotated[
        Literal["bestseller", "week_bestseller", "month_bestseller", "popular", "newest", "cheapest", "most_expensive"],
        Field(
            description="Order: bestseller (all time), week_bestseller, month_bestseller, popular, newest, cheapest / most_expensive (price to pay)."
        ),
    ] = "bestseller",
    kind: Kind = "any",
    category: Category = None,
    free_only: Annotated[bool, Field(description="Only free books.")] = False,
    plus_only: Annotated[bool, Field(description="Only books in the Fidibo Plus subscription.")] = False,
    min_price: MinPrice = None,
    max_price: MaxPrice = None,
    page: Page = 1,
    limit: Limit = 20,
) -> dict[str, Any]:
    """List books of a category (or all of Fidibo) in a chosen order, with optional free / Fidibo Plus / price filters.

    Use for "best audiobooks in psychology", "cheapest ebooks of a genre", "what is in Plus". Categories:
    fd_categories. Shortcuts: fd_bestsellers, fd_new, fd_free. By author or publisher: fd_author, fd_publisher.
    The price range is applied after fetching (up to 3 pages per call); more: pass next_page back as page.
    """
    return await book_list(
        sort=sort,
        kind=kind,
        category=category,
        free=free_only,
        plus=plus_only,
        min_price=min_price,
        max_price=max_price,
        page=page,
        limit=limit,
    )


@tool("Bestsellers")
async def fd_bestsellers(
    period: Annotated[
        Literal["week", "month", "all"], Field(description="Best sellers of the last week, last month or all time.")
    ] = "week",
    kind: Kind = "any",
    category: Category = None,
    limit: Limit = 20,
) -> dict[str, Any]:
    """Top-selling Fidibo books of the week, month or all time, optionally per kind and category, with prices in Toman.

    Use for "what is popular now" or "best audiobooks". Narrow by genre with a category slug (fd_categories).
    """
    sort = {"week": "week_bestseller", "month": "month_bestseller", "all": "bestseller"}[period]
    return await book_list(sort=sort, kind=kind, category=category, limit=limit)


@tool("New releases")
async def fd_new(kind: Kind = "any", category: Category = None, limit: Limit = 20) -> dict[str, Any]:
    """Newest Fidibo books and audiobooks, optionally per kind and category, with prices in Toman.

    Use for "new books this week" or "latest audiobooks". Details of one: fd_book.
    """
    return await book_list(sort="newest", kind=kind, category=category, limit=limit)


@tool("Free books")
async def fd_free(
    kind: Kind = "any",
    category: Category = None,
    sort: Annotated[
        Literal["popular", "bestseller", "newest"], Field(description="popular (default), bestseller or newest.")
    ] = "popular",
    limit: Limit = 20,
) -> dict[str, Any]:
    """Free ebooks and audiobooks on Fidibo (price 0), optionally per kind and category.

    Use for "free books to read or listen to". Free books can still be Fidibo Plus titles; check `in_plus`.
    """
    return await book_list(sort=sort, kind=kind, category=category, free=True, limit=limit)


@tool("Categories")
async def fd_categories(
    level: Annotated[
        Literal["ebooks", "audiobooks", "education", "magazines", "podcasts"],
        Field(description="Top level: ebooks (default), audiobooks, education, magazines or podcasts."),
    ] = "ebooks",
) -> dict[str, Any]:
    """List Fidibo's categories and sub-categories (slug + Persian title) of one top level.

    Use to find the `category` slug for fd_browse / fd_bestsellers / fd_new / fd_free, e.g. 'psychology'
    or 'story-foreign-drama'. Audiobook slugs are under level 'audiobooks'.
    """
    rows = result(await api("/flex/base-levels")) or []
    top = next((r for r in rows if r.get("level_zero_slug") == level), None)
    if top is None:
        raise ApiError(f"Unknown level '{level}'.")
    cats = [
        {
            "slug": c.get("slug"),
            "title": c.get("title"),
            "subcategories": [{"slug": s.get("slug"), "title": s.get("title")} for s in c.get("subcategories") or []],
        }
        for c in top.get("categories") or []
    ]
    return {"level": level, "title": top.get("title"), "count": len(cats), "categories": cats}

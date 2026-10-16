"""Finding books: search, browse a category / author / publisher list, bestsellers, new releases, free books, categories."""

from __future__ import annotations

import asyncio
import html
import re
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal
from urllib.parse import quote

from pydantic import Field

from .http import SITE, ApiError, api, result
from .registry import tool

Kind = Annotated[Literal["any", "ebook", "audio"], Field(description="ebook (epub/pdf), audio (mp3) or any.")]
Category = Annotated[
    str | None,
    Field(
        pattern=r"^[a-z0-9-]{2,80}(/[a-z0-9-]{2,80})?$",
        description="Slug from fd_categories, e.g. 'psychology'; audiobook level: 'audiobooks/story-foreign'. Includes sub-categories.",
    ),
]
MinPrice = Annotated[int | None, Field(ge=0, description="Min price to pay, Toman, e.g. 20000.")]
MaxPrice = Annotated[int | None, Field(ge=1, description="Max price to pay, Toman, e.g. 100000.")]
Limit = Annotated[int, Field(ge=1, le=30, description="Books per page.")]
Page = Annotated[int, Field(ge=1, le=200, description="From 1; pass next_page back.")]

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
SCAN_SIZE = 20  # minimum books per page when scanning, so a filtered call looks at 60 books whatever `limit` is
LEVELS = ("ebooks", "audiobooks", "education", "magazines", "podcasts")
LEVELS_TTL = 3600  # seconds; the category tree changes rarely

_TAG = re.compile(r"<[^>]*>|<[^>]*$")
_category_ids: dict[str, int] = {}
_levels: tuple[float, list[dict[str, Any]]] | None = None


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


def _slim(card: dict[str, Any]) -> dict[str, Any]:
    """Drop default values (absent = 0 / false / no discount) from a card that is already filtered."""
    if card.get("price") == card.get("final_price"):
        card.pop("price", None)  # no discount: price equals final_price
    for k in ("discount_pct", "free", "in_plus", "ratings_count"):
        if not card.get(k):
            card.pop(k, None)
    if card.get("available") is True:
        card.pop("available")
    return card


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
    fetch: Callable[[int, int], Awaitable[tuple[list[dict[str, Any]], int | None]]],
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
    scanned = 0
    next_page: int | None = None
    size = max(limit, SCAN_SIZE) if filtered else limit
    pages = range(page, page + (MAX_SCAN if filtered else 1))
    fetched = await asyncio.gather(*(fetch(n, size) for n in pages))  # the client's semaphore caps concurrency
    total = fetched[0][1]
    for n, (raw, _) in zip(pages, fetched, strict=True):
        scanned += 1
        books += [_slim(c) for c in map(_card, raw) if _keep(c, min_price, max_price, free, plus)]
        next_page = n + 1 if len(raw) >= size else None
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
        Field(description="relevance, cheapest / most_expensive (price to pay) or newest."),
    ] = "relevance",
    free_only: Annotated[bool, Field(description="Only free books.")] = False,
    plus_only: Annotated[bool, Field(description="Only Fidibo Plus books.")] = False,
    min_price: MinPrice = None,
    max_price: MaxPrice = None,
    page: Page = 1,
    limit: Limit = 10,
) -> dict[str, Any]:
    """Search ebooks and audiobooks by title, author or keyword; cards with price (Toman), rating, authors.

    Use first for "find the book X" / "how much is X". Details: fd_book. Reviews: fd_reviews.
    """
    _check_range(min_price, max_price)
    params: dict[str, Any] = {"query": query, "order": SEARCH_SORTS[sort], "size": limit}
    if types := CONTENT_TYPES[kind]:
        params["contentType"] = "[" + ",".join(map(str, types)) + "]"

    async def fetch(n: int, size: int) -> tuple[list[dict[str, Any]], int | None]:
        data = await api("/flex/search/list/content", {**params, "size": size, "page": n})
        rows = result(data) or []
        return [i for c in rows for i in c.get("items") or []], (data.get("data") or {}).get("total")

    return await _scan(
        fetch, page=page, limit=limit, min_price=min_price, max_price=max_price, free=free_only, plus=plus_only
    )


async def _category_id(category: str, kind: str) -> int:
    level, _, slug = category.rpartition("/")
    level = level or ("audiobooks" if kind == "audio" else "ebooks")
    if level not in LEVELS:
        raise ApiError(f"Unknown category level '{level}'. Use one of: {', '.join(LEVELS)}.")
    key = f"{level}/{slug}"
    if key not in _category_ids:
        data = await api(f"/flex/{level}/categories/{quote(slug, safe='')}")
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
    limit: int = 10,
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

    async def fetch(n: int, size: int) -> tuple[list[dict[str, Any]], int | None]:
        data = await api("/flex/list/book", {"page": n, "limit": size}, body=body)
        return result(data) or [], None

    # free / plus are server-side here; only the price range is filtered after fetching.
    return await _scan(fetch, page=page, limit=limit, min_price=min_price, max_price=max_price)


@tool("Browse book lists")
async def fd_browse(
    sort: Annotated[
        Literal["bestseller", "week_bestseller", "month_bestseller", "popular", "newest", "cheapest", "most_expensive"],
        Field(
            description="bestseller (all time), week_ / month_bestseller, popular, newest, cheapest / most_expensive."
        ),
    ] = "bestseller",
    kind: Kind = "any",
    category: Category = None,
    free_only: Annotated[bool, Field(description="Only free books.")] = False,
    plus_only: Annotated[bool, Field(description="Only Fidibo Plus books.")] = False,
    min_price: MinPrice = None,
    max_price: MaxPrice = None,
    page: Page = 1,
    limit: Limit = 10,
) -> dict[str, Any]:
    """List books of a category (or all) in a chosen order, with free / Plus / price filters.

    Use for "best audiobooks in psychology", "cheapest ebooks of a genre". Slugs: fd_categories.
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
        Literal["week", "month", "all"], Field(description="Last week, last month or all time.")
    ] = "week",
    kind: Kind = "any",
    category: Category = None,
    limit: Limit = 10,
) -> dict[str, Any]:
    """Top sellers of the week, month or all time, per kind and category (Toman).

    Use for "what is popular now" or "best audiobooks". Genre slugs: fd_categories.
    """
    sort = {"week": "week_bestseller", "month": "month_bestseller", "all": "bestseller"}[period]
    return await book_list(sort=sort, kind=kind, category=category, limit=limit)


@tool("New releases")
async def fd_new(kind: Kind = "any", category: Category = None, limit: Limit = 10) -> dict[str, Any]:
    """Newest books and audiobooks, per kind and category (Toman).

    Use for "new books this week" or "latest audiobooks". Details: fd_book.
    """
    return await book_list(sort="newest", kind=kind, category=category, limit=limit)


@tool("Free books")
async def fd_free(
    kind: Kind = "any",
    category: Category = None,
    sort: Annotated[
        Literal["popular", "bestseller", "newest"], Field(description="Order of the free books.")
    ] = "popular",
    limit: Limit = 10,
) -> dict[str, Any]:
    """Free ebooks and audiobooks (price 0), per kind and category.

    Use for "free books to read or listen to". Free books can still be Plus titles (`in_plus`).
    """
    return await book_list(sort=sort, kind=kind, category=category, free=True, limit=limit)


@tool("Categories")
async def fd_categories(
    level: Annotated[
        Literal["ebooks", "audiobooks", "education", "magazines", "podcasts"],
        Field(description="Top level (default ebooks)."),
    ] = "ebooks",
    parent: Annotated[
        str | None,
        Field(pattern=r"^[a-z0-9-]{2,80}$", description="Only this category's sub-categories, e.g. 'psychology'."),
    ] = None,
) -> dict[str, Any]:
    """List category and sub-category slugs (with Persian titles) of one top level.

    Use to find the `category` slug for fd_browse / fd_bestsellers / fd_new / fd_free, e.g. 'story-foreign-drama'.
    Audiobook slugs are under level 'audiobooks'. Pass `parent` to narrow a large tree.
    """
    global _levels
    if _levels is None or time.monotonic() - _levels[0] > LEVELS_TTL:
        _levels = (time.monotonic(), result(await api("/flex/base-levels")) or [])
    top = next((r for r in _levels[1] if r.get("level_zero_slug") == level), None)
    if top is None:
        raise ApiError(f"Unknown level '{level}'.")
    cats = [
        {
            "slug": c.get("slug"),
            "title": c.get("title"),
            "subcategories": [{"slug": s.get("slug"), "title": s.get("title")} for s in c.get("subcategories") or []],
        }
        for c in top.get("categories") or []
        if parent is None or c.get("slug") == parent
    ]
    if parent and not cats:
        raise ApiError(f"Category '{parent}' not found in '{level}'. List top-level slugs without `parent`.")
    return {"level": level, "title": top.get("title"), "count": len(cats), "categories": cats}

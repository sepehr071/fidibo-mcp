"""One book: full record, reader reviews, and similar books."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any
from urllib.parse import quote

from pydantic import Field

from .books import _card, _slim, _slug, _text, book_list
from .http import ApiError, api, result
from .registry import tool

BookId = Annotated[int, Field(ge=1, le=100_000_000, description="From fd_search / fd_browse, e.g. 68286.")]

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


FullText = Annotated[bool, Field(description="Do not clip description or review text.")]


def _clip(text: str, n: int | None) -> str | None:
    return (text[:n] + "…" if n and len(text) > n else text) or None


def _toman(text: str | None) -> int | None:
    """'۶۰۰۰۰ تومان' -> 60000."""
    digits = "".join(ch for ch in (text or "").translate(_DIGITS) if ch.isdigit())
    return int(digits) if digits else None


async def _item(book_id: int) -> dict[str, Any]:
    items = result(await api(f"/flex/book/item/{book_id}")) or []
    if not items:
        raise ApiError(f"Book {book_id} not found on Fidibo. Find books with fd_search.")
    return items[0]


def _component(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    comp = next((r for r in rows if r.get("component") == name), None)
    return ((comp or {}).get("items") or [{}])[0]


@tool("Book details")
async def fd_book(book_id: BookId, full_text: FullText = False) -> dict[str, Any]:
    """One book's full record: price (Toman), format, pages or duration, size, people, rating and star
    distribution, Plus flag, description (cut at 1500 chars unless full_text), printed price, category.

    Use after fd_search / fd_browse once the user picks a book. Then fd_reviews, fd_similar, fd_author.
    """
    item, overview = await asyncio.gather(
        _item(book_id), api("/flex/page", {"pageName": "BOOK_OVERVIEW", "bookId": book_id, "page": 1, "limit": 15})
    )
    rows = result(overview) or []
    specs = {
        s["title"]: s["sub_title"]
        for s in _component(rows, "BOOK_SPECIFICATION").get("specifications") or []
        if s.get("title") and s.get("sub_title") and not s.get("action")
    }
    rate = _component(rows, "BOOK_RATE")
    crumbs = [b for b in item.get("breadcrumb") or [] if (b.get("action") or {}).get("type") == "category_page"]
    out = _card(item)
    out.update(
        {
            "pages": int(item["pages_count"]) if str(item.get("pages_count") or "").isdigit() else None,
            "file_size": specs.get("حجم"),
            "language": specs.get("زبان"),
            "original_title": item.get("original_title") or specs.get("عنوان انگلیسی"),
            "published": specs.get("تاریخ انتشار"),
            "printed_price": _toman(specs.get("قیمت چاپی")),
            "usd_price": item.get("price_usd"),
            "campaign_pct": (item.get("campaign") or {}).get("discount_amount"),
            "categories": [b["name"] for b in crumbs],
            "category_id": crumbs[-1]["id"] if crumbs else None,
            "reviews_count": rate.get("reviews"),
            "rating_distribution_pct": {str(d["score"]): d["percent"] for d in rate.get("distribution") or []},
            "moods": [f"{c['title']} ({c['responses']})" for c in rate.get("choices") or []],
            "description": _clip(
                _text(_component(rows, "BOOK_INTRODUCTION").get("introduction", {}).get("description")),
                None if full_text else 1500,
            ),
            "slug": _slug(item),
        }
    )
    return _slim({k: v for k, v in out.items() if v not in (None, [], {})})


@tool("Book reviews")
async def fd_reviews(
    book_id: BookId,
    page: Annotated[int, Field(ge=1, le=100, description="From 1.")] = 1,
    limit: Annotated[int, Field(ge=1, le=20, description="Reviews per page.")] = 10,
    full_text: FullText = False,
) -> dict[str, Any]:
    """Reader reviews of a book: text (cut at 400 chars unless full_text), 1-5 stars, date, likes, replies, total count.

    Use to judge quality beyond the average rating (fd_book has the distribution).
    """
    item = await _item(book_id)
    slug = _slug(item) or str(book_id)
    data = await api(f"/flex/book/reviews/{quote(slug, safe='')}", {"page": page, "limit": limit})
    total = (data.get("data") or {}).get("total") or 0
    reviews = [
        {
            "user": _clip(str(r.get("user") or ""), 40),
            "date": r.get("time"),
            "rating": r.get("rate"),
            "text": _clip((r.get("body") or "").strip(), None if full_text else 400),
            "likes": r.get("likes_count") or 0,
            "replies": r.get("comments_count") or 0,
        }
        for r in result(data) or []
    ]
    return {
        "book": _text(item.get("title")),
        "total_reviews": total,
        "count": len(reviews),
        "reviews": reviews,
        "next_page": page + 1 if page * limit < total else None,
    }


@tool("Similar books")
async def fd_similar(
    book_id: BookId,
    same_kind: Annotated[bool, Field(description="Only the same kind (ebook / audiobook).")] = True,
    limit: Annotated[int, Field(ge=1, le=30, description="Max books.")] = 10,
) -> dict[str, Any]:
    """Books like this one: bestsellers of its category, the book itself left out (Toman).

    Use for "what else like X" or an audio alternative (same_kind=False). No real similar-books endpoint exists.
    """
    item = await _item(book_id)
    crumbs = [b for b in item.get("breadcrumb") or [] if (b.get("action") or {}).get("type") == "category_page"]
    kind = "any"
    if same_kind:
        kind = "audio" if item.get("content_type") in ("audiobook", "micro_audiobook") else "ebook"
    for crumb in reversed(crumbs):  # leaf category first, then its parents until something comes back
        found = await book_list(
            sort="bestseller", kind=kind, category_id=crumb["id"], exclude_id=book_id, limit=min(limit + 1, 30)
        )
        books = [b for b in found["books"] if b["id"] != book_id][:limit]
        if books:
            return {
                "based_on": {"book": _text(item.get("title")), "category": crumb["name"]},
                "count": len(books),
                "books": books,
            }
    return {"based_on": {"book": _text(item.get("title"))}, "count": 0, "books": []}

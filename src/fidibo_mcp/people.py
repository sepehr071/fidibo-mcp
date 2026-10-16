"""Authors, translators, narrators and publishers, with their books."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal

from pydantic import Field

from .books import Kind, Limit, _text, book_list
from .detail import FullText, _clip
from .http import SITE, ApiError, api, result
from .registry import tool

Sort = Annotated[
    Literal["bestseller", "newest", "popular", "cheapest"],
    Field(description="Order of the books (default bestseller)."),
]


async def _resolve(who: int | str, kind: str) -> tuple[int, list[dict[str, Any]]]:
    """An id, or a name looked up through search. Returns (id, other_matches)."""
    if isinstance(who, str) and who.strip().isdigit():
        who = int(who)
    if isinstance(who, int):
        return who, []
    data = await api(f"/flex/search/list/{kind}", {"query": who, "page": 1, "size": 5})
    matches = [i for c in result(data) or [] for i in c.get("items") or []][:5]
    if not matches:
        raise ApiError(f"No {kind} found for '{who}'. Try another spelling, or search books with fd_search.")
    key = "title" if kind == "publisher" else "name"
    return matches[0]["id"], [{"id": m["id"], "name": _text(m.get(key))} for m in matches]


@tool("Author or translator")
async def fd_author(
    author: Annotated[
        Annotated[int, Field(ge=1, le=100_000_000)] | Annotated[str, Field(min_length=1, max_length=100)],
        Field(description="Person id (e.g. 30198) or a name (e.g. 'اگزوپری'); authors, translators, narrators."),
    ],
    sort: Sort = "bestseller",
    kind: Kind = "any",
    limit: Limit = 10,
) -> dict[str, Any]:
    """An author's, translator's or narrator's profile and books (Toman).

    Use for "books by X" or "what has Y narrated". A name uses the first match; `matches` lists the others (call
    again with an id to pick one). Details: fd_book.
    """
    person_id, matches = await _resolve(author, "person")
    profile, books = await asyncio.gather(
        api(f"/flex/persons/{person_id}"), book_list(sort=sort, kind=kind, author_id=person_id, limit=limit)
    )
    rows = result(profile) or []
    if not rows:
        raise ApiError(f"Person {person_id} not found on Fidibo.")
    p = rows[0]
    out = {
        "id": p["id"],
        "name": p.get("full_name"),
        "roles": p.get("roles") or [],
        "url": p.get("share_url") or f"{SITE}/contributors/{p.get('slug')}",
        "matches": matches[1:] or None,
        "books": books["books"],
        "next_page": books["next_page"],
    }
    return {k: v for k, v in out.items() if v is not None}


@tool("Publisher")
async def fd_publisher(
    publisher: Annotated[
        Annotated[int, Field(ge=1, le=100_000_000)] | Annotated[str, Field(min_length=1, max_length=100)],
        Field(description="Publisher id (e.g. 221) or a name (e.g. 'نگاه')."),
    ],
    sort: Sort = "bestseller",
    kind: Kind = "any",
    limit: Limit = 10,
    full_text: FullText = False,
) -> dict[str, Any]:
    """A publisher's profile and books (Toman).

    Use for "books from publisher X". A name uses the first match; `matches` lists the others. Details: fd_book.
    """
    publisher_id, matches = await _resolve(publisher, "publisher")
    profile, books = await asyncio.gather(
        api(f"/flex/publishers/{publisher_id}"),
        book_list(sort=sort, kind=kind, publisher_id=publisher_id, limit=limit),
    )
    rows = result(profile) or []
    if not rows:
        raise ApiError(f"Publisher {publisher_id} not found on Fidibo.")
    p = rows[0]
    desc = _text(p.get("description"))
    out = {
        "id": p["id"],
        "name": p.get("name"),
        "description": _clip(desc, None if full_text else 600),
        "logo": p.get("image"),
        "url": f"{SITE}/publishers/{p.get('slug')}",
        "matches": matches[1:] or None,
        "books": books["books"],
        "next_page": books["next_page"],
    }
    return {k: v for k, v in out.items() if v is not None}

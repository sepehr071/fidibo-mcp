import pytest

pytestmark = [pytest.mark.anyio, pytest.mark.live]


async def call(client, name, args):
    result = await client.call_tool(name, args)
    assert not result.is_error, result.content[0].text
    return result.structured_content


async def _popular_book(client, kind="ebook") -> dict:
    """Books come and go: take a current bestseller."""
    return (await call(client, "fd_bestsellers", {"period": "all", "kind": kind, "limit": 5}))["books"][0]


async def test_fd_book_ebook_and_audiobook(client):
    ebook = await _popular_book(client)
    data = await call(client, "fd_book", {"book_id": ebook["id"]})
    assert data["id"] == ebook["id"] and data["type"] in ("ebook", "microbook") and data["final_price"] <= data["price"]
    assert (
        data["pages"]
        and data["file_size"]
        and data["category_id"]
        and data["description"]
        and data["reviews_count"] > 0
    )
    assert set(data["rating_distribution_pct"]) == {"1", "2", "3", "4", "5"}
    audio = await _popular_book(client, "audio")
    data = await call(client, "fd_book", {"book_id": audio["id"]})
    assert data["type"] == "audiobook" and data["duration"] and data["narrators"]


async def test_fd_reviews(client):
    book = await _popular_book(client)
    data = await call(client, "fd_reviews", {"book_id": book["id"], "limit": 5})
    assert data["total_reviews"] > 0 and data["reviews"] and data["next_page"] in (2, None)
    assert all(r["text"] and 1 <= r["rating"] <= 5 for r in data["reviews"])


async def test_fd_similar(client):
    book = await _popular_book(client)
    data = await call(client, "fd_similar", {"book_id": book["id"], "limit": 8})
    assert data["books"] and book["id"] not in [b["id"] for b in data["books"]]
    assert all(b["type"] in ("ebook", "microbook") for b in data["books"])

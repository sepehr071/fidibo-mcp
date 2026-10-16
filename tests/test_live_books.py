import pytest

pytestmark = [pytest.mark.anyio, pytest.mark.live]


async def call(client, name, args):
    result = await client.call_tool(name, args)
    assert not result.is_error, result.content[0].text
    return result.structured_content


def check_cards(books):
    assert books
    for b in books:
        assert b["id"] and b["title"] and b["url"].startswith("https://fidibo.com/book/")
        price = b.get("price", b["final_price"])  # price is omitted when it equals final_price
        assert b["final_price"] <= price and b.get("free", False) == (b["final_price"] == 0 and price == 0)
        assert b["image"].startswith("https://")


async def test_fd_search(client):
    data = await call(client, "fd_search", {"query": "شازده کوچولو", "sort": "cheapest", "limit": 10})
    check_cards(data["books"])
    assert data["total_matches"] > 10 and data["next_page"] == 2
    assert any("شازده" in b["title"] for b in data["books"])
    prices = [b["final_price"] for b in data["books"]]  # sorted by the price to pay
    assert prices == sorted(prices)
    audio = await call(client, "fd_search", {"query": "شازده کوچولو", "kind": "audio", "limit": 10})
    assert all(b["type"] in ("audiobook", "micro_audiobook") for b in audio["books"])
    cheap = await call(client, "fd_search", {"query": "شازده کوچولو", "max_price": 20000, "limit": 20})
    assert all(b["final_price"] <= 20000 for b in cheap["books"])


async def test_fd_browse(client):
    cats = await call(client, "fd_categories", {"level": "ebooks"})
    slug = cats["categories"][0]["subcategories"][0]["slug"]
    data = await call(client, "fd_browse", {"category": slug, "sort": "cheapest", "kind": "ebook", "limit": 10})
    check_cards(data["books"])
    prices = [b["final_price"] for b in data["books"]]
    assert prices == sorted(prices)
    plus = await call(client, "fd_browse", {"plus_only": True, "kind": "audio", "limit": 10})
    assert all(b["in_plus"] and b["type"] == "audiobook" for b in plus["books"])


async def test_fd_bestsellers(client):
    data = await call(client, "fd_bestsellers", {"period": "week", "kind": "audio", "limit": 10})
    check_cards(data["books"])
    assert all(b["type"] in ("audiobook", "micro_audiobook") for b in data["books"])


async def test_fd_new(client):
    check_cards((await call(client, "fd_new", {"kind": "ebook", "limit": 10}))["books"])


async def test_fd_free(client):
    data = await call(client, "fd_free", {"limit": 10})
    check_cards(data["books"])
    assert all(b.get("free") and b["final_price"] == 0 for b in data["books"])


async def test_fd_categories(client):
    data = await call(client, "fd_categories", {"level": "audiobooks"})
    assert data["count"] >= 5 and data["categories"][0]["slug"] and data["categories"][0]["subcategories"]
    audio = await call(
        client, "fd_bestsellers", {"kind": "audio", "category": data["categories"][0]["slug"], "limit": 5}
    )
    check_cards(audio["books"])

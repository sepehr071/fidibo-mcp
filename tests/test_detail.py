import json

import httpx
import pytest
from conftest import fixture

pytestmark = pytest.mark.anyio

SLUG_PATH = "/flex/book/reviews/68286-کتاب-شازده-کوچولو"


async def test_fd_book_ebook(client, api):
    api["/flex/book/item/68286"] = fixture("book_item_ebook.json")
    api["/flex/page"] = fixture("overview_ebook.json")
    out = (await client.call_tool("fd_book", {"book_id": 68286})).structured_content
    overview = next(c for c in api.calls if c.url.path == "/flex/page")
    assert overview.url.params["pageName"] == "BOOK_OVERVIEW" and overview.url.params["bookId"] == "68286"
    # the site shows 49,000 crossed out and 44,100 تومان, printed price 60000 تومان
    assert (out["price"], out["final_price"], out["discount_pct"], out["campaign_pct"]) == (49000, 44100, 10, 10)
    assert out["printed_price"] == 60000 and out["usd_price"] == 3
    assert out["type"] == "ebook" and out["file_format"] == "epub" and out["pages"] == 128
    assert (
        out["file_size"] == "۱.۹۱ مگابایت" and out["language"] == "فارسی" and out["original_title"] == "Le petit prince"
    )
    assert (
        out["authors"] == "آنتوان دوسنت اگزوپری" and out["translators"] == "پرویز شهدی" and out["publisher"] == "مجید"
    )
    assert out["in_plus"] is True and out["free"] is False and out["rating"] == 4.3
    assert out["categories"] == ["داستان و رمان", "داستان و رمان خارجی", "درام"] and out["category_id"] == 449
    assert out["reviews_count"] == 67 and out["rating_distribution_pct"]["1"] == 4
    assert out["description"].startswith("کتاب شازده کوچولو اثر") and "<" not in out["description"]


async def test_fd_book_audiobook(client, api):
    api["/flex/book/item/88132"] = fixture("book_item_audio.json")
    api["/flex/page"] = fixture("overview_audio.json")
    out = (await client.call_tool("fd_book", {"book_id": 88132})).structured_content
    assert out["type"] == "audiobook" and out["duration"] == "01:30:32" and out["file_size"] == "۶۲.۱۶ مگابایت"
    assert out["narrators"].startswith("ابوالحسن تهامی") and "pages" not in out
    assert (out["price"], out["final_price"], out["discount_pct"]) == (200000, 200000, 0)
    assert "printed_price" not in out


async def test_fd_book_not_found(client, api):
    result = await client.call_tool("fd_book", {"book_id": 99999999})
    assert result.is_error and "HTTP 404" in result.content[0].text


async def test_fd_reviews_uses_the_slug(client, api):
    api["/flex/book/item/68286"] = fixture("book_item_ebook.json")
    api[SLUG_PATH] = fixture("reviews.json")
    out = (await client.call_tool("fd_reviews", {"book_id": 68286, "limit": 3})).structured_content
    assert api.params() == {"page": "1", "limit": "3"}
    assert out["total_reviews"] == 62 and out["count"] == 3 and out["next_page"] == 2
    first = out["reviews"][0]
    assert first["user"] == "عارف علیخانی" and first["rating"] == 3 and first["likes"] == 18 and first["replies"] == 1
    assert first["text"].startswith("توش به مفاهیمی")


async def test_fd_reviews_last_page(client, api):
    api["/flex/book/item/68286"] = fixture("book_item_ebook.json")
    api[SLUG_PATH] = fixture("reviews.json")
    out = (await client.call_tool("fd_reviews", {"book_id": 68286, "page": 21, "limit": 3})).structured_content
    assert out["next_page"] is None


async def test_fd_similar_uses_leaf_category_and_excludes_the_book(client, api):
    api["/flex/book/item/68286"] = fixture("book_item_ebook.json")
    api["/flex/list/book"] = fixture("list_category.json")
    out = (await client.call_tool("fd_similar", {"book_id": 68286, "limit": 3})).structured_content
    assert api.body() == {"order": "BESTSELLER", "contentType": [1, 6], "categoryId": [449], "excludeBookId": [68286]}
    assert out["based_on"] == {"book": "شازده کوچولو", "category": "درام"} and out["count"] == 3
    assert 68286 not in [b["id"] for b in out["books"]]


async def test_fd_similar_falls_back_to_parent_category(client, api):
    api["/flex/book/item/68286"] = fixture("book_item_ebook.json")

    def by_category(request):
        if json.loads(request.content)["categoryId"] == [449]:
            return httpx.Response(204)
        return httpx.Response(200, json=fixture("list_category.json"))

    api["/flex/list/book"] = by_category
    out = (await client.call_tool("fd_similar", {"book_id": 68286, "same_kind": False})).structured_content
    assert out["based_on"]["category"] == "داستان و رمان خارجی" and out["count"] == 4
    assert "contentType" not in api.body()

import pytest
from conftest import fixture

pytestmark = pytest.mark.anyio

LIST = "/flex/list/book"


async def test_fd_author_by_id(client, api):
    api["/flex/persons/30198"] = fixture("person.json")
    api[LIST] = fixture("list_category.json")
    out = (await client.call_tool("fd_author", {"author": 30198, "sort": "newest", "kind": "audio"})).structured_content
    assert api.body() == {"order": "RECENT", "contentType": [2, 7], "authorId": [30198]}
    assert out["id"] == 30198 and out["name"] == "آنتوان دوسنت اگزوپری" and out["roles"] == ["نویسنده"]
    assert out["url"].startswith("https://fidibo.com/contributors/30198") and len(out["books"]) == 4
    assert "matches" not in out


async def test_fd_author_by_name_lists_other_matches(client, api):
    api["/flex/search/list/person"] = fixture("search_person.json")
    api["/flex/persons/30198"] = fixture("person.json")
    api[LIST] = fixture("list_category.json")
    out = (await client.call_tool("fd_author", {"author": "اگزوپری"})).structured_content
    assert api.params(0) == {"query": "اگزوپری", "page": "1", "size": "5"}
    assert out["id"] == 30198
    assert out["matches"][0] == {"id": 652, "name": "آنتوان دو سنت اگزوپری"}  # <b> markup removed


async def test_fd_author_digit_string_is_an_id(client, api):
    api["/flex/persons/30198"] = fixture("person.json")
    api[LIST] = fixture("list_category.json")
    out = (await client.call_tool("fd_author", {"author": "30198"})).structured_content
    assert out["id"] == 30198 and api.calls[0].url.path == "/flex/persons/30198"


async def test_fd_author_not_found(client, api):
    api["/flex/search/list/person"] = {"data": {"result": [], "total": 0}}
    result = await client.call_tool("fd_author", {"author": "zzzz"})
    assert result.is_error and "No person found" in result.content[0].text


async def test_fd_publisher_by_name(client, api):
    api["/flex/search/list/publisher"] = fixture("search_publisher.json")
    api["/flex/publishers/221"] = fixture("publisher.json")
    api[LIST] = fixture("list_category.json")
    out = (await client.call_tool("fd_publisher", {"publisher": "مجید"})).structured_content
    assert api.body() == {"order": "BESTSELLER", "publisherId": [221]}
    assert out["id"] == 221 and out["name"] == "مجید" and out["logo"].startswith("https://cdn.fidibo.com/")
    assert "<" not in out["description"] and len(out["books"]) == 4
    assert out["url"] == "https://fidibo.com/publishers/221-انتشارات-مجید"


async def test_fd_publisher_full_text(client, api):
    profile = fixture("publisher.json")
    profile["data"]["result"][0]["description"] = "z" * 1000
    api["/flex/publishers/221"] = profile
    api[LIST] = fixture("list_category.json")
    clipped = (await client.call_tool("fd_publisher", {"publisher": 221})).structured_content
    full = (await client.call_tool("fd_publisher", {"publisher": 221, "full_text": True})).structured_content
    assert clipped["description"] == "z" * 600 + "…" and full["description"] == "z" * 1000

import httpx
import pytest
from conftest import fixture

pytestmark = pytest.mark.anyio

SEARCH = "/flex/search/list/content"
LIST = "/flex/list/book"


async def test_fd_search_cards_prices_and_params(client, api):
    api[SEARCH] = fixture("search_list.json")
    out = (await client.call_tool("fd_search", {"query": "شازده کوچولو", "sort": "cheapest"})).structured_content
    assert api.params() == {"query": "شازده کوچولو", "order": "LOWEST_PRICE", "size": "10", "page": "1"}
    assert out["count"] == 6 and out["next_page"] is None
    free, plain, discounted = out["books"][0], out["books"][1], out["books"][2]
    assert free["free"] is True and free["final_price"] == 0 and free["id"] == 186478
    assert (plain["final_price"], plain["in_plus"]) == (5000, True)
    assert "price" not in plain and "discount_pct" not in plain and "available" not in plain  # defaults are dropped
    assert (discounted["price"], discounted["final_price"], discounted["discount_pct"]) == (10000, 5000, 50)
    assert discounted["type"] == "audiobook" and discounted["publisher"] == "آوارسا"
    assert (
        "in_plus" not in out["books"][4] and "free" not in out["books"][4] and "rating" not in out["books"][4]
    )  # nobody rated it
    assert plain["url"] == "https://fidibo.com/book/123825-شازده-کوچولو" and "<b>" not in plain["title"]
    assert all(b["image"].startswith("http") for b in out["books"])  # covers stay on every card


async def test_fd_search_kind_sets_content_types(client, api):
    api[SEARCH] = fixture("search_list.json")
    await client.call_tool("fd_search", {"query": "کتاب", "kind": "audio", "sort": "newest", "page": 2, "limit": 5})
    assert api.params() == {
        "query": "کتاب",
        "order": "RECENT",
        "size": "5",
        "page": "2",
        "contentType": "[2,7]",
    }


async def test_fd_search_client_side_filters(client, api):
    api[SEARCH] = fixture("search_list.json")

    async def ids(**args):
        out = (await client.call_tool("fd_search", {"query": "شازده", **args})).structured_content
        assert "after fetching" in out["note"]
        return [b["id"] for b in out["books"]]

    assert await ids(max_price=5000) == [186478, 123825, 91415, 175267]  # price to pay, free included
    assert await ids(min_price=6000) == [128352, 151101]
    assert await ids(free_only=True) == [186478]
    assert await ids(plus_only=True) == [186478, 123825, 91415, 151101]


async def test_fd_search_scans_several_pages_for_filters(client, api, monkeypatch):
    monkeypatch.setattr("fidibo_mcp.books.SCAN_SIZE", 1)
    rows = fixture("search_list.json")["data"]["result"][0]["items"]

    def pages(request):
        n = int(request.url.params["page"])
        items = rows[(n - 1) * 2 : n * 2]
        return httpx.Response(200, json={"data": {"total": 6, "result": [{"items": items}]}})

    api[SEARCH] = pages
    out = (await client.call_tool("fd_search", {"query": "xx", "limit": 2, "max_price": 5000})).structured_content
    assert [c.url.path for c in api.calls] == [SEARCH] * 3 and api.params(2)["page"] == "3"
    assert [b["id"] for b in out["books"]] == [186478, 123825, 91415, 175267]
    assert out["next_page"] == 4 and out["total_matches"] == 6


async def test_fd_search_bad_range(client):
    result = await client.call_tool("fd_search", {"query": "xx", "min_price": 9, "max_price": 3})
    assert result.is_error and "higher than max_price" in result.content[0].text


async def test_fd_browse_category_resolves_id_and_filters(client, api):
    api["/flex/audiobooks/categories/story-foreign"] = {
        "data": {"result": {"action": {"inputs": [{"key": "categoryId", "value": "210"}]}}}
    }
    api[LIST] = fixture("list_plus_audio.json")
    out = (
        await client.call_tool(
            "fd_browse",
            {"category": "story-foreign", "kind": "audio", "plus_only": True, "sort": "week_bestseller", "limit": 4},
        )
    ).structured_content
    assert api.body() == {
        "order": "WEEK_BESTSELLER",
        "contentType": [2, 7],
        "categoryId": [210],
        "subscription_only": True,
    }
    assert api.params() == {"page": "1", "limit": "4"}
    assert [b["id"] for b in out["books"]] == [84590, 79932, 87739, 93755] and out["next_page"] == 2
    assert out["books"][0]["final_price"] == 166500 and out["books"][0]["discount_pct"] == 10


async def test_fd_browse_category_id_is_cached_and_level_from_slug(client, api):
    api["/flex/ebooks/categories/story-foreign-drama"] = fixture("category_drama.json")
    api[LIST] = fixture("list_category.json")
    for _ in range(2):
        await client.call_tool("fd_browse", {"category": "story-foreign-drama", "kind": "ebook"})
    assert [c.url.path for c in api.calls].count("/flex/ebooks/categories/story-foreign-drama") == 1
    assert api.body() == {"order": "BESTSELLER", "contentType": [1, 6], "categoryId": [449]}


async def test_fd_browse_price_range_after_fetch(client, api, monkeypatch):
    monkeypatch.setattr("fidibo_mcp.books.SCAN_SIZE", 1)
    page_one = fixture("list_category.json")
    api[LIST] = lambda r: httpx.Response(200, json=page_one) if r.url.params["page"] == "1" else httpx.Response(204)
    out = (await client.call_tool("fd_browse", {"max_price": 120000, "limit": 4})).structured_content
    assert [b["id"] for b in out["books"]] == [6673, 68283]  # 64664 costs 126,000 after its 30% campaign
    assert len(api.calls) == 3 and out["next_page"] is None  # 3 pages fetched together
    assert "contentType" not in api.body()


async def test_fd_browse_unknown_category(client, api):
    result = await client.call_tool("fd_browse", {"category": "nope"})
    assert result.is_error and "HTTP 404" in result.content[0].text


async def test_fd_free(client, api):
    api[LIST] = fixture("list_free.json")
    out = (await client.call_tool("fd_free", {"kind": "ebook", "limit": 4})).structured_content
    assert api.body() == {"order": "POPULAR", "contentType": [1, 6], "free": True}
    assert out["count"] == 4 and all(b["free"] and b["final_price"] == 0 for b in out["books"])


@pytest.mark.parametrize(
    ("period", "order"), [("week", "WEEK_BESTSELLER"), ("month", "MONTH_BESTSELLER"), ("all", "BESTSELLER")]
)
async def test_fd_bestsellers_periods(client, api, period, order):
    api[LIST] = fixture("list_category.json")
    out = (await client.call_tool("fd_bestsellers", {"period": period})).structured_content
    assert api.body() == {"order": order} and out["count"] == 4
    assert out["books"][2]["discount_pct"] == 30 and out["books"][2]["final_price"] == 126000


async def test_fd_new(client, api):
    api[LIST] = fixture("list_category.json")
    await client.call_tool("fd_new", {"kind": "audio"})
    assert api.body() == {"order": "RECENT", "contentType": [2, 7]}


async def test_fd_categories(client, api):
    api["/flex/base-levels"] = fixture("base_levels.json")
    out = (await client.call_tool("fd_categories", {"level": "audiobooks"})).structured_content
    assert out["level"] == "audiobooks" and out["count"] == 3
    assert out["categories"][0]["slug"] == "story-foreign"
    assert {"slug": "story-foreign-drama", "title": "درام"} in out["categories"][0]["subcategories"]


async def test_result_is_one_compact_text_block(client, api):
    api[SEARCH] = fixture("search_list.json")
    result = await client.call_tool("fd_search", {"query": "شازده"})
    text = result.content[0].text
    assert len(result.content) == 1 and text.startswith('{"count":') and "\n" not in text
    assert "شازده" in text and "\\u0" not in text


async def test_fd_categories_parent_filter_and_cache(client, api):
    api["/flex/base-levels"] = fixture("base_levels.json")
    out = (
        await client.call_tool("fd_categories", {"level": "audiobooks", "parent": "story-foreign"})
    ).structured_content
    assert out["count"] == 1 and out["categories"][0]["slug"] == "story-foreign"
    bad = await client.call_tool("fd_categories", {"level": "audiobooks", "parent": "nope-nope"})
    assert bad.is_error and "not found" in bad.content[0].text
    assert len(api.calls) == 1  # the category tree is cached


async def test_unknown_category_level_is_rejected(client, api):
    result = await client.call_tool("fd_browse", {"category": "evil/psychology"})
    assert result.is_error and "Unknown category level" in result.content[0].text and not api.calls


async def test_filtered_scan_uses_at_least_scan_size_per_page(client, api):
    api[SEARCH] = fixture("search_list.json")
    await client.call_tool("fd_search", {"query": "xx", "max_price": 5000})  # default limit 10
    assert {api.params(i)["size"] for i in range(3)} == {"20"}
    await client.call_tool("fd_search", {"query": "xx"})
    assert api.params(3)["size"] == "10"

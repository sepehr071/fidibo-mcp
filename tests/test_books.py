import httpx
import pytest
from conftest import fixture

pytestmark = pytest.mark.anyio

SEARCH = "/flex/search/list/content"
LIST = "/flex/list/book"


async def test_fd_search_cards_prices_and_params(client, api):
    api[SEARCH] = fixture("search_list.json")
    out = (await client.call_tool("fd_search", {"query": "شازده کوچولو", "sort": "cheapest"})).structured_content
    assert api.params() == {"query": "شازده کوچولو", "order": "LOWEST_PRICE", "size": "20", "page": "1"}
    assert out["count"] == 6 and out["next_page"] is None
    free, plain, discounted = out["books"][0], out["books"][1], out["books"][2]
    assert free["free"] is True and free["final_price"] == 0 and free["id"] == 186478
    assert (plain["price"], plain["final_price"], plain["discount_pct"], plain["in_plus"]) == (5000, 5000, 0, True)
    assert (discounted["price"], discounted["final_price"], discounted["discount_pct"]) == (10000, 5000, 50)
    assert discounted["type"] == "audiobook" and discounted["publisher"] == "آوارسا"
    assert out["books"][4]["in_plus"] is False and "rating" not in out["books"][4]  # nobody rated it
    assert plain["url"] == "https://fidibo.com/book/123825-شازده-کوچولو" and "<b>" not in plain["title"]


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


async def test_fd_search_scans_several_pages_for_filters(client, api):
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


async def test_fd_browse_price_range_after_fetch(client, api):
    page_one = fixture("list_category.json")
    api[LIST] = lambda r: httpx.Response(200, json=page_one) if r.url.params["page"] == "1" else httpx.Response(204)
    out = (await client.call_tool("fd_browse", {"max_price": 120000, "limit": 4})).structured_content
    assert [b["id"] for b in out["books"]] == [6673, 68283]  # 64664 costs 126,000 after its 30% campaign
    assert len(api.calls) == 2 and out["next_page"] is None
    assert "contentType" not in api.body()


async def test_fd_browse_unknown_category(client, api):
    result = await client.call_tool("fd_browse", {"category": "nope"})
    assert result.is_error and "HTTP 404" in result.content[0].text


async def test_fd_free(client, api):
    api[LIST] = fixture("list_free.json")
    out = (await client.call_tool("fd_free", {"kind": "ebook", "limit": 4})).structured_content
    assert api.body() == {"order": "POPULAR", "contentType": [1, 6], "free": True}
    assert out["count"] == 4 and all(b["free"] and b["final_price"] == 0 and b["price"] == 0 for b in out["books"])


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

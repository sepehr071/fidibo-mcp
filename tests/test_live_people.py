import pytest

pytestmark = [pytest.mark.anyio, pytest.mark.live]


async def call(client, name, args):
    result = await client.call_tool(name, args)
    assert not result.is_error, result.content[0].text
    return result.structured_content


async def test_fd_author(client):
    by_id = await call(client, "fd_author", {"author": 30198, "limit": 5})
    assert by_id["name"] == "آنتوان دوسنت اگزوپری" and by_id["books"]
    by_name = await call(client, "fd_author", {"author": "اگزوپری", "sort": "cheapest", "limit": 5})
    assert by_name["books"] and by_name["matches"]


async def test_fd_publisher(client):
    by_id = await call(client, "fd_publisher", {"publisher": 221, "limit": 5})
    assert by_id["name"] == "مجید" and by_id["books"] and by_id["description"]
    by_name = await call(client, "fd_publisher", {"publisher": "نشر مجید", "kind": "ebook", "limit": 5})
    assert by_name["id"] and by_name["books"]

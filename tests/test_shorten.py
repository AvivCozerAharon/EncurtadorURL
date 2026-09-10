async def test_shorten_returns_short_code_and_short_url(client):
    response = await client.post(
        "/shorten", json={"url": "https://example.com/some/long/path"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["original_url"] == "https://example.com/some/long/path"
    assert len(data["short_code"]) == 6
    assert data["short_url"].endswith(data["short_code"])


async def test_shorten_missing_url_returns_422(client):
    response = await client.post("/shorten", json={})
    assert response.status_code == 422


async def test_shorten_invalid_url_returns_422(client):
    response = await client.post("/shorten", json={"url": "not-a-url"})
    assert response.status_code == 422


async def test_shorten_same_url_twice_gives_different_codes(client):
    first = await client.post("/shorten", json={"url": "https://example.com"})
    second = await client.post("/shorten", json={"url": "https://example.com"})
    assert first.json()["short_code"] != second.json()["short_code"]

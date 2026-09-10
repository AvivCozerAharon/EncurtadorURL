import itertools

from sqlalchemy.exc import OperationalError

import main


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


async def test_collision_retry_recovers(client, monkeypatch):
    seq = itertools.chain(["AAAAAA", "AAAAAA", "BBBBBB"], itertools.repeat("CCCCCC"))
    monkeypatch.setattr(main, "generate_short_code", lambda *a, **k: next(seq))

    await client.post("/shorten", json={"url": "https://a.example.com/1"})
    r2 = await client.post("/shorten", json={"url": "https://b.example.com/2"})

    assert r2.status_code == 200
    assert r2.json()["short_code"] == "BBBBBB"


async def test_db_failure_returns_503(client, monkeypatch):
    async def boom(*args, **kwargs):
        raise OperationalError("stmt", {}, Exception("connection refused"))

    monkeypatch.setattr("sqlalchemy.ext.asyncio.AsyncSession.commit", boom)

    response = await client.post("/shorten", json={"url": "https://z.example.com/"})

    assert response.status_code == 503

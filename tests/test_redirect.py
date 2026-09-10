from sqlalchemy import select

from db import Link, SessionLocal


async def test_redirect_to_original_url(client):
    shorten = await client.post(
        "/shorten", json={"url": "https://example.com/target"}
    )
    code = shorten.json()["short_code"]

    response = await client.get(f"/{code}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/target"


async def test_redirect_unknown_code_returns_404(client):
    response = await client.get("/abcdef", follow_redirects=False)
    assert response.status_code == 404


async def test_redirect_increments_hits(client):
    shorten = await client.post(
        "/shorten", json={"url": "https://example.com/counted"}
    )
    code = shorten.json()["short_code"]

    await client.get(f"/{code}", follow_redirects=False)
    await client.get(f"/{code}", follow_redirects=False)

    async with SessionLocal() as session:
        result = await session.execute(select(Link).where(Link.short_code == code))
        link = result.scalar_one()
        assert link.hits == 2

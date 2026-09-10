import logging
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import AnyHttpUrl, BaseModel
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db import Link, SessionLocal, get_session, init_db
from shortcode import generate_short_code

app = FastAPI()

logger = logging.getLogger(__name__)

MAX_SHORT_CODE_ATTEMPTS = 5
STATIC_DIR = Path(__file__).parent / "static"


@app.on_event("startup")
async def on_startup() -> None:
    await init_db()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


class ShortenRequest(BaseModel):
    url: AnyHttpUrl


class ShortenResponse(BaseModel):
    original_url: str
    short_code: str
    short_url: str


@app.post("/shorten", response_model=ShortenResponse)
async def shorten_url(
    payload: ShortenRequest, session: AsyncSession = Depends(get_session)
) -> ShortenResponse:
    original_url = str(payload.url)

    for _ in range(MAX_SHORT_CODE_ATTEMPTS):
        code = generate_short_code()
        session.add(Link(original_url=original_url, short_code=code))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            continue
        except SQLAlchemyError:
            await session.rollback()
            raise HTTPException(status_code=503, detail="Database unavailable")
        return ShortenResponse(
            original_url=original_url,
            short_code=code,
            short_url=f"http://localhost:8000/{code}",
        )

    raise HTTPException(
        status_code=500, detail="Could not generate a unique short code"
    )


async def _increment_hits(link_id: int) -> None:
    try:
        async with SessionLocal() as session:
            await session.execute(
                update(Link).where(Link.id == link_id).values(hits=Link.hits + 1)
            )
            await session.commit()
    except SQLAlchemyError:
        logger.warning("could not increment hits for link_id=%s", link_id)


@app.get("/{short_code}")
async def redirect_to_original(
    short_code: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    try:
        result = await session.execute(
            select(Link).where(Link.short_code == short_code)
        )
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")

    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="Short URL not found")

    background_tasks.add_task(_increment_hits, link.id)
    return RedirectResponse(url=link.original_url, status_code=302)

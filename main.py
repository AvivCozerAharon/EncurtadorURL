from fastapi import Depends, FastAPI, HTTPException
from pydantic import AnyHttpUrl, BaseModel
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db import Link, get_session, init_db
from shortcode import generate_short_code

app = FastAPI()

MAX_SHORT_CODE_ATTEMPTS = 5


@app.on_event("startup")
async def on_startup() -> None:
    await init_db()


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

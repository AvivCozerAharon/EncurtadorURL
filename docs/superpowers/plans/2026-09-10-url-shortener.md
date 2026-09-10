# Encurtador de URLs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a URL shortener API (FastAPI + Postgres + Docker Compose) that generates 6-character short codes, redirects to original URLs with a hit counter, and ships with a README answering the professor's availability/consistency/performance questions.

**Architecture:** A single FastAPI app (`main.py`) with two endpoints (`POST /shorten`, `GET /{short_code}`) backed by a `links` table accessed through SQLAlchemy's async engine (asyncpg in production, aiosqlite in tests). Short codes are generated randomly and uniqueness is enforced by a database `UNIQUE` constraint with retry-on-collision, not application locking. The hit counter is incremented in a `BackgroundTask` that runs after the redirect response is already sent.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), asyncpg (prod), aiosqlite (tests), Pydantic, pytest + pytest-asyncio + httpx, Docker / Docker Compose, PostgreSQL 16.

**Spec:** `docs/superpowers/specs/2026-09-10-url-shortener-design.md`

## Global Constraints

- Short codes are exactly 6 characters, alphabet `[A-Za-z0-9]` (base62).
- Uniqueness of `short_code` is guaranteed by a DB `UNIQUE` constraint; the app retries on collision, it does not pre-check.
- Redirect responses use HTTP 302, never 301.
- The hit counter (`hits`) increments via `BackgroundTask` after the redirect response is sent — it must never block the redirect.
- Any database connectivity failure surfaces as HTTP 503, not a generic 500.
- No Redis, no cache layer, no Alembic migrations — `Base.metadata.create_all` on startup is sufficient for this project.
- Tests run against SQLite (aiosqlite) via `DATABASE_URL` override, never require a live Postgres.

---

### Task 1: Database layer and project setup

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `db.py`
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`
- Create: `tests/test_db.py`
- Create: `pytest.ini`
- Create: `.gitignore`

**Interfaces:**
- Produces: `db.py` exposes `engine` (AsyncEngine), `SessionLocal` (async_sessionmaker), `Base` (DeclarativeBase), `Link` (model with `id: int`, `original_url: str`, `short_code: str`, `hits: int`, `created_at`), `init_db()` (async, creates tables), `get_session()` (async generator FastAPI dependency yielding an `AsyncSession`).
- `tests/conftest.py` produces an autouse `_reset_db` fixture (drops/creates tables before each test) that later test files rely on implicitly.

- [ ] **Step 1: Create requirements files**

`requirements.txt`:
```
fastapi
uvicorn[standard]
sqlalchemy[asyncio]>=2.0
asyncpg
pydantic
```

`requirements-dev.txt`:
```
-r requirements.txt
aiosqlite
pytest
pytest-asyncio
httpx
```

- [ ] **Step 2: Create `.gitignore`**

```
venv/
__pycache__/
*.pyc
.env
*.db
```

- [ ] **Step 3: Write `db.py`**

```python
import os
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://shortener:shortener@localhost:5432/shortener",
)

engine = create_async_engine(DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    short_code: Mapped[str] = mapped_column(
        String(6), unique=True, nullable=False, index=True
    )
    hits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session():
    async with SessionLocal() as session:
        yield session
```

- [ ] **Step 4: Write `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 5: Write `tests/conftest.py`**

This must set `DATABASE_URL` to a temp-file SQLite database **before** `db.py` is ever imported by any test module, since `db.py` reads the env var at import time.

```python
import os
import tempfile

_tmp_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{os.path.join(_tmp_dir, 'test.db')}"

import pytest_asyncio  # noqa: E402

from db import Base, engine  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _reset_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
```

- [ ] **Step 6: Create empty `tests/__init__.py`**

Empty file (marks `tests/` as a package so imports resolve consistently).

- [ ] **Step 7: Write the failing test `tests/test_db.py`**

```python
import pytest
from sqlalchemy.exc import IntegrityError

from db import Link, SessionLocal


async def test_short_code_unique_constraint():
    async with SessionLocal() as session:
        session.add(Link(original_url="https://a.com", short_code="abc123"))
        await session.commit()

        session.add(Link(original_url="https://b.com", short_code="abc123"))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_hits_defaults_to_zero():
    async with SessionLocal() as session:
        link = Link(original_url="https://a.com", short_code="zzz999")
        session.add(link)
        await session.commit()
        await session.refresh(link)
        assert link.hits == 0
```

- [ ] **Step 8: Install dev dependencies**

Run: `pip install -r requirements-dev.txt`

- [ ] **Step 9: Run the test to verify it passes**

Run: `pytest tests/test_db.py -v`
Expected: both tests PASS (this task has no separate "write failing test first" step since it's exercising a DB constraint, not driving new production code — the model in Step 3 already implements the behavior under test).

- [ ] **Step 10: Commit**

```bash
git add requirements.txt requirements-dev.txt db.py pytest.ini .gitignore tests/
git commit -m "feat: add database layer with Link model and test setup"
```

---

### Task 2: Short code generator

**Files:**
- Create: `shortcode.py`
- Create: `tests/test_shortcode.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `shortcode.py` exposes `generate_short_code(length: int = 6) -> str`. Task 4 (shorten endpoint) calls this with no arguments.

- [ ] **Step 1: Write the failing tests**

```python
from shortcode import generate_short_code


def test_generate_short_code_default_length():
    code = generate_short_code()
    assert len(code) == 6


def test_generate_short_code_custom_length():
    code = generate_short_code(length=10)
    assert len(code) == 10


def test_generate_short_code_alphanumeric():
    code = generate_short_code()
    assert code.isalnum()


def test_generate_short_code_is_random():
    codes = {generate_short_code() for _ in range(200)}
    assert len(codes) == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_shortcode.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shortcode'`

- [ ] **Step 3: Write `shortcode.py`**

```python
import secrets
import string

_ALPHABET = string.ascii_letters + string.digits


def generate_short_code(length: int = 6) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_shortcode.py -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add shortcode.py tests/test_shortcode.py
git commit -m "feat: add random base62 short code generator"
```

---

### Task 3: POST /shorten endpoint

**Files:**
- Modify: `main.py` (replace placeholder content entirely)
- Create: `tests/test_shorten.py`
- Modify: `tests/conftest.py` (add shared `client` fixture)

**Interfaces:**
- Consumes: `db.get_session`, `db.Link`, `db.SessionLocal` from Task 1; `shortcode.generate_short_code` from Task 2.
- Produces: `main.py` exposes `app` (FastAPI instance). Task 4 adds the redirect route to this same `app` and reuses its imports.

- [ ] **Step 1: Add the shared `client` fixture to `tests/conftest.py`**

Append to the existing file from Task 1:

```python
from httpx import ASGITransport, AsyncClient

from main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
```

- [ ] **Step 2: Write the failing tests in `tests/test_shorten.py`**

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_shorten.py -v`
Expected: FAIL (`main.py` still has the old placeholder code, `/shorten` doesn't match this contract)

- [ ] **Step 4: Replace `main.py` with the shorten endpoint**

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_shorten.py -v`
Expected: all 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add main.py tests/conftest.py tests/test_shorten.py
git commit -m "feat: add POST /shorten endpoint with collision retry"
```

---

### Task 4: GET /{short_code} redirect endpoint

**Files:**
- Modify: `main.py` (add redirect route)
- Create: `tests/test_redirect.py`

**Interfaces:**
- Consumes: `app` from Task 3; `db.Link`, `db.SessionLocal`, `db.get_session` from Task 1.
- Produces: nothing further consumed by later tasks.

- [ ] **Step 1: Write the failing tests in `tests/test_redirect.py`**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_redirect.py -v`
Expected: FAIL with 404/405 (no route for `GET /{short_code}` yet)

- [ ] **Step 3: Add the redirect route to `main.py`**

Add these imports to the top of `main.py` (merge with existing `fastapi`/`sqlalchemy` imports rather than duplicating):

```python
from fastapi import BackgroundTasks
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update

from db import SessionLocal
```

Append to `main.py`:

```python
async def _increment_hits(link_id: int) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(Link).where(Link.id == link_id).values(hits=Link.hits + 1)
        )
        await session.commit()


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_redirect.py -v`
Expected: all 3 tests PASS

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: all tests across `test_db.py`, `test_shortcode.py`, `test_shorten.py`, `test_redirect.py` PASS

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_redirect.py
git commit -m "feat: add GET /{short_code} redirect with background hit counter"
```

---

### Task 5: Dockerize the application

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`

**Interfaces:**
- Consumes: `requirements.txt`, `main.py`, `db.py`, `shortcode.py` (all files copied into the image).
- Produces: a running stack reachable at `http://localhost:8000`, verified manually (this task has no pytest step — it's verified via `docker compose` commands).

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py db.py shortcode.py ./

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: shortener
      POSTGRES_PASSWORD: shortener
      POSTGRES_DB: shortener
    volumes:
      - db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U shortener"]
      interval: 5s
      timeout: 5s
      retries: 5

  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://shortener:shortener@db:5432/shortener
    depends_on:
      db:
        condition: service_healthy

volumes:
  db_data:
```

- [ ] **Step 3: Write `.env.example`**

```
DATABASE_URL=postgresql+asyncpg://shortener:shortener@localhost:5432/shortener
```

- [ ] **Step 4: Build and start the stack**

Run: `docker compose up --build -d`
Expected: both `db` and `app` containers reach `running`/`healthy` state (`docker compose ps`)

- [ ] **Step 5: Manually verify the shorten endpoint**

Run:
```bash
curl -s -X POST http://localhost:8000/shorten -H "Content-Type: application/json" -d "{\"url\": \"https://google.com\"}"
```
Expected: JSON response with `short_code` of length 6

- [ ] **Step 6: Manually verify the redirect endpoint**

Run (replace `abc123` with the `short_code` from Step 5):
```bash
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" http://localhost:8000/abc123
```
Expected: `302 https://google.com/`

- [ ] **Step 7: Verify persistence across restarts**

Run: `docker compose restart app` then repeat Step 6.
Expected: same 302 result — data survived the app container restart because it lives in the `db` container's volume, not in the app.

- [ ] **Step 8: Tear down**

Run: `docker compose down`

- [ ] **Step 9: Commit**

```bash
git add Dockerfile docker-compose.yml .env.example
git commit -m "feat: dockerize app and postgres via docker compose"
```

---

### Task 6: README with setup instructions and architecture answers

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: nothing consumed by other tasks — this is the final task.

- [ ] **Step 1: Write `README.md`**

```markdown
# Encurtador de URLs

API de encurtamento de URLs em FastAPI, com persistência em PostgreSQL,
rodando em Docker Compose.

## Como rodar

\`\`\`bash
docker compose up --build
\`\`\`

A API sobe em `http://localhost:8000`.

### Encurtar uma URL

\`\`\`bash
curl -X POST http://localhost:8000/shorten \\
  -H "Content-Type: application/json" \\
  -d '{"url": "https://google.com"}'
\`\`\`

Resposta:

\`\`\`json
{
  "original_url": "https://google.com",
  "short_code": "aZ3kP9",
  "short_url": "http://localhost:8000/aZ3kP9"
}
\`\`\`

### Acessar o link curto

Acessar `http://localhost:8000/aZ3kP9` no navegador (ou `curl -L`) redireciona
(HTTP 302) para a URL original e incrementa o contador de acessos em segundo
plano.

## Rodando os testes

\`\`\`bash
pip install -r requirements-dev.txt
pytest -v
\`\`\`

Os testes rodam contra um banco SQLite temporário (via `aiosqlite`), não
exigem um Postgres real.

## Desafio de Arquitetura

**Disponibilidade.** Se o Postgres ficar fora do ar por 10 segundos, todo
redirect de um link já existente falha com HTTP 503. A URL original só
existe no banco — não há como servir o redirecionamento sem ele nesta
arquitetura. Isso é uma limitação real do design atual (um único banco,
sem réplica ou cache de leitura); mitigá-la exigiria um cache-aside
(Redis, ou até um cache em memória) na frente do Postgres, o que ficou
fora do escopo desta entrega.

**Consistência.** A geração do código curto não depende de nenhuma
coordenação entre requisições: cada requisição gera 6 caracteres
aleatórios (base62, ~56 bilhões de combinações) e tenta inserir no
banco. A unicidade é garantida pelo `UNIQUE` constraint na coluna
`short_code` — se dois usuários submeterem URLs no mesmo milissegundo e,
por azar, gerarem o mesmo código, o banco rejeita a segunda inserção
(`IntegrityError`) e a aplicação simplesmente gera outro código e tenta
de novo. O banco é a fonte da verdade sobre unicidade, não a aplicação.

**Desempenho.** O `INSERT`/`UPDATE` no Postgres é mais lento que apenas
devolver um redirect. Para o `GET /{short_code}`, a aplicação primeiro
busca a URL original (`SELECT`) e devolve o HTTP 302 imediatamente; o
incremento do contador de hits (`UPDATE`) roda depois, em uma
`BackgroundTask`, então a latência dessa escrita nunca é percebida por
quem está sendo redirecionado. Ainda assim, como a API e o banco estão
no mesmo "monolito" (mesmo processo, mesma conexão de rede até o
Postgres), um pico de escrita nos contadores de hits ainda pode
competir por conexões de banco com as leituras de redirect — separar
esses dois caminhos exigiria filas ou um serviço de contagem à parte,
também fora do escopo desta entrega.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add setup instructions and architecture answers"
```

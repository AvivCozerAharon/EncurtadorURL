# Encurtador de URLs — Design

## Contexto

Tarefa de faculdade (Sistemas Distribuídos): construir um encurtador de
URLs com API que gera códigos curtos de 6 caracteres e redireciona para
a URL original, rodando em Docker com persistência em SQL. O entregável
inclui um README respondendo três provocações arquiteturais
(disponibilidade, consistência, desempenho).

## Stack

- **Linguagem/framework:** Python + FastAPI (já iniciado em `main.py`)
- **Banco:** PostgreSQL 16, container separado via Docker Compose
- **Acesso a dados:** SQLAlchemy async + asyncpg
- **Orquestração:** Docker Compose (serviços `app` e `db`)

## Modelo de dados

Tabela `links`:

| campo | tipo | descrição |
|---|---|---|
| id | serial PK | identificador único |
| original_url | text | URL de destino |
| short_code | varchar(6) UNIQUE | código curto |
| hits | integer default 0 | contador de acessos |
| created_at | timestamptz default now() | data de criação |

## API

### `POST /shorten`

- Request: `{"url": "https://..."}`
- Valida que `url` foi enviado e tem forma minimamente válida (esquema http/https).
- Gera um código de 6 caracteres aleatórios em base62 (`[A-Za-z0-9]`).
- Tenta `INSERT`; se violar o UNIQUE constraint de `short_code`, gera outro
  código e tenta novamente (poucas tentativas — espaço de 62^6 ≈ 56 bilhões).
- Resposta: `{"original_url", "short_code", "short_url"}`.

### `GET /{short_code}`

- `SELECT original_url, id FROM links WHERE short_code = :code`.
- Se não encontrado: 404.
- Se encontrado: responde imediatamente com `RedirectResponse(url=original_url, status_code=302)`
  e dispara um `BackgroundTask` que executa `UPDATE links SET hits = hits + 1 WHERE id = :id`
  **depois** da resposta ter sido enviada ao cliente — o usuário não espera
  pela escrita do contador.
- 302 (não 301) para que o navegador não cacheie o redirect e o contador de
  hits continue preciso em cliques repetidos.

### Tratamento de erros

- Qualquer falha de conexão com o Postgres (timeout, connection refused)
  em qualquer endpoint retorna 503 com mensagem clara, em vez de vazar
  como 500 genérico.

## Docker

- `Dockerfile` para a app (Python slim, instala deps, roda uvicorn).
- `docker-compose.yml`:
  - `db`: `postgres:16`, volume nomeado para persistência, healthcheck
    (`pg_isready`).
  - `app`: build local, `depends_on: db` com `condition: service_healthy`,
    variáveis de ambiente para a connection string (via `.env`).
- `.env.example` documentando as variáveis esperadas.

## README — respostas às provocações

O README deve incluir, além de instruções de setup:

1. **Disponibilidade:** se o Postgres cair por 10s, qualquer redirect
   falha com 503 — a URL original só existe no banco, não há como
   servir sem ele nesta arquitetura. Isso é uma limitação real do
   design monolítico atual; mitigações possíveis (cache de leitura,
   réplica) ficam fora do escopo desta entrega.
2. **Consistência:** a geração do código é aleatória e a unicidade é
   garantida pelo `UNIQUE` constraint no banco, não por lógica da
   aplicação — se dois usuários colidirem no mesmo milissegundo, o
   banco rejeita a segunda inserção e a aplicação tenta outro código.
3. **Desempenho:** o incremento do contador de hits roda em
   `BackgroundTask` após a resposta de redirect já ter sido enviada,
   então a latência de escrita no banco não afeta a experiência do
   usuário sendo redirecionado — mas ainda compartilha o mesmo banco e
   processo que a leitura, o que é discutido como trade-off do
   "monolito".

## Fora de escopo

- Cache (Redis ou em memória)
- Autenticação/rate limiting
- Migrations com Alembic (schema criado via `Base.metadata.create_all`
  no startup, suficiente para este projeto)

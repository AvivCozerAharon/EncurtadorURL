# Encurtador de URLs

API de encurtamento de URLs em FastAPI, com persistência em PostgreSQL,
rodando em Docker Compose.

## Como rodar

```bash
docker compose up --build
```

A API sobe em `http://localhost:8000`.

### Encurtar uma URL

```bash
curl -X POST http://localhost:8000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://google.com"}'
```

Resposta:

```json
{
  "original_url": "https://google.com",
  "short_code": "aZ3kP9",
  "short_url": "http://localhost:8000/aZ3kP9"
}
```

### Acessar o link curto

Acessar `http://localhost:8000/aZ3kP9` no navegador (ou `curl -L`) redireciona
(HTTP 302) para a URL original e incrementa o contador de acessos em segundo
plano.

## Rodando os testes

```bash
pip install -r requirements-dev.txt
pytest -v
```

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

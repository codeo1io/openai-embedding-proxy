# OpenAI Embedding Proxy

A minimal Dockerized proxy for OpenAI embeddings. It intentionally exposes only the embedding endpoint and only allows the `text-embedding-3-small` model.

## Behavior

- Accepts `POST /v1/embeddings` (OpenAI-compatible path).
- Also accepts `POST /v1/embedding` as a singular alias.
- Requires `Authorization: Bearer <anything>` from callers, but accepts any non-empty bearer token.
- Requires the request body to contain `"model": "text-embedding-3-small"`.
- Relays the request body to OpenAI's `https://api.openai.com/v1/embeddings` using the server-side OpenAI key.
- Rejects every other model.
- Does not expose chat, completions, models, docs, OpenAPI, health, or other application endpoints.
- Never returns the configured upstream OpenAI API key.

## Deploy with Docker Compose

Clone the repository on the target VM, then:

```bash
cp example.env .env
$EDITOR .env

docker compose up -d --build
```

Set `OPENAI_API_KEY` in `.env` to the real OpenAI key. `.env` is gitignored and must never be committed.

The proxy listens on port `8080` by default.

## Docker run

```bash
docker build -t openai-embedding-proxy .
docker run -d \
  --name openai-embedding-proxy \
  --restart unless-stopped \
  -p 8080:8080 \
  -e OPENAI_API_KEY='YOUR_REAL_OPENAI_KEY' \
  openai-embedding-proxy
```

You can also provide the upstream key through a mounted file instead of an environment variable:

```bash
docker run -d \
  --name openai-embedding-proxy \
  --restart unless-stopped \
  -p 8080:8080 \
  -v /secure/path/openai_key:/run/secrets/openai_key:ro \
  -e OPENAI_API_KEY_FILE=/run/secrets/openai_key \
  openai-embedding-proxy
```

## Request example

Any non-empty bearer token is accepted from the client:

```bash
curl http://HOST:8080/v1/embeddings \
  -H 'Authorization: Bearer anything-at-all' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "text-embedding-3-small",
    "input": "hello world"
  }'
```

The singular alias is also accepted:

```bash
curl http://HOST:8080/v1/embedding \
  -H 'Authorization: Bearer arbitrary-key' \
  -H 'Content-Type: application/json' \
  -d '{"model":"text-embedding-3-small","input":"hello world"}'
```

## Rejection examples

A different model returns HTTP 400 without calling OpenAI:

```json
{
  "detail": "Only model 'text-embedding-3-small' is allowed"
}
```

Missing or malformed bearer auth returns HTTP 401. Any unrelated endpoint returns HTTP 404, and unsupported methods on the allowed paths return HTTP 405.

## Local tests

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

The test suite uses a mocked upstream response, so it does not consume OpenAI API credits or require the real upstream key.

## Security notes

This proxy deliberately does **not** authenticate callers beyond requiring a syntactically valid non-empty bearer token. Anyone who can reach the service can use the stored OpenAI key indirectly for `text-embedding-3-small` requests. Restrict network access to trusted hosts or networks.

The upstream URL is fixed in code to OpenAI's embedding endpoint to prevent callers from turning the service into a general-purpose HTTP proxy.

# OpenAI Embedding Proxy

A minimal Dockerized proxy for OpenAI embeddings. It only proxies embedding requests for `text-embedding-3-small` and includes a tiny web page for saving the upstream OpenAI API key.

## Behavior

- Accepts `POST /v1/embeddings` (OpenAI-compatible path).
- Also accepts `POST /v1/embedding` as a singular alias.
- Requires `Authorization: Bearer <anything>` from callers, but accepts any non-empty bearer token.
- Requires the request body to contain `"model": "text-embedding-3-small"`.
- Relays the request body to OpenAI's `https://api.openai.com/v1/embeddings` using the server-side OpenAI key.
- Rejects every other model.
- Exposes a minimal `GET /` web UI and `POST /admin/api-key` save action for configuring the upstream key.
- Does not expose chat, completions, models, docs, OpenAPI, health, or any other proxy endpoints.
- Never returns or displays the configured upstream OpenAI API key.
- Stores UI-saved keys in `/data/openai_api_key` with mode `0600`; Docker Compose mounts `/data` from a named volume so the key survives container restarts, recreation, and host reboots.

## Deploy with Docker Compose

Clone the repository on the target VM, then:

```bash
docker compose up -d --build
```

Open `http://HOST:18473/`, paste the OpenAI API key, and press **Save key**. The key is stored in the `embedding_proxy_data` Docker volume and is not written to GitHub or the image.

You may optionally set `OPENAI_API_KEY` as a bootstrap/fallback environment variable. Once a key has been saved through the web UI, the persisted key takes precedence.

The proxy listens on port `18473` by default.

## Docker run

```bash
docker build -t openai-embedding-proxy .
docker volume create embedding_proxy_data
docker run -d \
  --name openai-embedding-proxy \
  --restart unless-stopped \
  -p 18473:18473 \
  -v embedding_proxy_data:/data \
  openai-embedding-proxy
```

Then open `http://HOST:18473/` and save the OpenAI API key. The named volume keeps it across container restarts/recreation and host reboots.

You can also provide the upstream key through a mounted file instead of using the web UI:

```bash
docker run -d \
  --name openai-embedding-proxy \
  --restart unless-stopped \
  -p 18473:18473 \
  -v /secure/path/openai_key:/run/secrets/openai_key:ro \
  -e OPENAI_API_KEY_FILE=/run/secrets/openai_key \
  openai-embedding-proxy
```

## Request example

Any non-empty bearer token is accepted from the client:

```bash
curl http://HOST:18473/v1/embeddings \
  -H 'Authorization: Bearer anything-at-all' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "text-embedding-3-small",
    "input": "hello world"
  }'
```

The singular alias is also accepted:

```bash
curl http://HOST:18473/v1/embedding \
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

This proxy deliberately does **not** authenticate callers beyond requiring a syntactically valid non-empty bearer token. Anyone who can reach the service can use the stored OpenAI key indirectly for `text-embedding-3-small` requests. The lightweight key-management page is also intentionally unauthenticated, so anyone who can reach it can replace the stored upstream key. Restrict network access to trusted hosts or networks.

The upstream URL is fixed in code to OpenAI's embedding endpoint to prevent callers from turning the service into a general-purpose HTTP proxy.

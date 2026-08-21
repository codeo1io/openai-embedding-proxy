import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response

ALLOWED_MODEL = "text-embedding-3-small"
UPSTREAM_URL = "https://api.openai.com/v1/embeddings"

app = FastAPI(
    title="OpenAI Embedding Proxy",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def _read_openai_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    key_file = os.getenv("OPENAI_API_KEY_FILE", "").strip()

    if key:
        return key
    if key_file:
        try:
            return Path(key_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(f"Unable to read OPENAI_API_KEY_FILE: {exc}") from exc
    raise RuntimeError("OPENAI_API_KEY or OPENAI_API_KEY_FILE must be configured")


def _validate_caller_auth(authorization: str | None) -> None:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    scheme, sep, token = authorization.partition(" ")
    if not sep or scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Use Authorization: Bearer <any-non-empty-key>")


async def _send_upstream(payload: dict[str, Any]) -> httpx.Response:
    api_key = _read_openai_key()
    timeout = float(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "60"))
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(
            UPSTREAM_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )


async def _handle_embeddings(request: Request, authorization: str | None) -> Response:
    _validate_caller_auth(authorization)

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    model = payload.get("model")
    if model != ALLOWED_MODEL:
        raise HTTPException(
            status_code=400,
            detail=f"Only model '{ALLOWED_MODEL}' is allowed",
        )

    try:
        upstream = await _send_upstream(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="OpenAI upstream timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="OpenAI upstream request failed") from exc

    content_type = upstream.headers.get("content-type", "application/json")
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers={"content-type": content_type},
    )


@app.post("/v1/embeddings")
async def embeddings_plural(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Response:
    return await _handle_embeddings(request, authorization)


@app.post("/v1/embedding")
async def embeddings_singular(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Response:
    return await _handle_embeddings(request, authorization)

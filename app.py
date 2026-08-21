import os
import tempfile
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

ALLOWED_MODEL = "text-embedding-3-small"
UPSTREAM_URL = "https://api.openai.com/v1/embeddings"
DEFAULT_KEY_FILE = "/data/openai_api_key"

app = FastAPI(
    title="OpenAI Embedding Proxy",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def _key_path() -> Path:
    return Path(os.getenv("OPENAI_API_KEY_FILE", DEFAULT_KEY_FILE))


def _read_openai_key() -> str:
    key_file = _key_path()
    if key_file.exists():
        try:
            key = key_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(f"Unable to read OPENAI_API_KEY_FILE: {exc}") from exc
        if key:
            return key

    key = os.getenv("OPENAI_API_KEY", "").strip()
    if key:
        return key

    raise RuntimeError("OpenAI API key is not configured")


def _save_openai_key(key: str) -> None:
    key = key.strip()
    if not key:
        raise ValueError("API key must not be empty")

    key_file = _key_path()
    key_file.parent.mkdir(parents=True, exist_ok=True)

    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=key_file.parent,
            prefix=".openai_key.",
            delete=False,
        ) as temp:
            temp.write(key)
            temp.flush()
            os.fsync(temp.fileno())
            temp_name = temp.name

        os.chmod(temp_name, 0o600)
        os.replace(temp_name, key_file)
    except OSError as exc:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass
        raise RuntimeError(f"Unable to persist OpenAI API key: {exc}") from exc


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


@app.get("/", response_class=HTMLResponse)
async def key_ui() -> HTMLResponse:
    configured = False
    try:
        _read_openai_key()
        configured = True
    except RuntimeError:
        pass

    state = "Configured" if configured else "Not configured"
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Embedding Proxy Key</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:440px;margin:12vh auto;padding:0 18px;color:#202124}}
form{{display:grid;gap:12px}}input,button{{font:inherit;padding:12px;border-radius:8px;border:1px solid #bbb}}
button{{cursor:pointer}}small{{color:#666}}#msg{{min-height:1.4em}}
</style>
</head>
<body>
<h2>OpenAI API key</h2>
<small>Status: {state}. Saved keys are never displayed.</small>
<form id="keyForm">
<input id="apiKey" type="password" autocomplete="off" placeholder="OpenAI API key" required>
<button type="submit">Save key</button>
<div id="msg"></div>
</form>
<script>
const form=document.getElementById('keyForm'),input=document.getElementById('apiKey'),msg=document.getElementById('msg');
form.addEventListener('submit',async(e)=>{{e.preventDefault();msg.textContent='Saving…';
const r=await fetch('/admin/api-key',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{api_key:input.value}})}});
const j=await r.json().catch(()=>({{}}));
if(r.ok){{input.value='';msg.textContent='Saved.';}}else{{msg.textContent=j.detail||'Save failed.';}}
}});
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.post("/admin/api-key")
async def save_key(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("api_key"), str):
        raise HTTPException(status_code=400, detail="api_key must be a string")

    try:
        _save_openai_key(payload["api_key"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse({"saved": True})


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

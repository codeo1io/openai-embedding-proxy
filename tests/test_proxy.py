import json
from unittest.mock import AsyncMock

import httpx
from fastapi.testclient import TestClient

import app as proxy

client = TestClient(proxy.app)


def _upstream_response(status_code=200, payload=None):
    if payload is None:
        payload = {
            "object": "list",
            "data": [{"object": "embedding", "embedding": [0.1, 0.2], "index": 0}],
            "model": proxy.ALLOWED_MODEL,
            "usage": {"prompt_tokens": 1, "total_tokens": 1},
        }
    request = httpx.Request("POST", proxy.UPSTREAM_URL)
    return httpx.Response(
        status_code,
        content=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        request=request,
    )


def test_missing_auth_is_rejected():
    response = client.post(
        "/v1/embeddings",
        json={"model": proxy.ALLOWED_MODEL, "input": "hello"},
    )
    assert response.status_code == 401


def test_any_nonempty_bearer_key_is_accepted(monkeypatch):
    mocked = AsyncMock(return_value=_upstream_response())
    monkeypatch.setattr(proxy, "_send_upstream", mocked)

    response = client.post(
        "/v1/embeddings",
        headers={"Authorization": "Bearer literally-any-key"},
        json={"model": proxy.ALLOWED_MODEL, "input": "hello"},
    )

    assert response.status_code == 200
    mocked.assert_awaited_once()
    forwarded_payload = mocked.await_args.args[0]
    assert forwarded_payload["model"] == proxy.ALLOWED_MODEL
    assert forwarded_payload["input"] == "hello"


def test_singular_embedding_alias_is_accepted(monkeypatch):
    monkeypatch.setattr(proxy, "_send_upstream", AsyncMock(return_value=_upstream_response()))

    response = client.post(
        "/v1/embedding",
        headers={"Authorization": "Bearer abc"},
        json={"model": proxy.ALLOWED_MODEL, "input": ["hello", "world"]},
    )

    assert response.status_code == 200


def test_other_model_is_rejected_without_upstream_call(monkeypatch):
    mocked = AsyncMock(return_value=_upstream_response())
    monkeypatch.setattr(proxy, "_send_upstream", mocked)

    response = client.post(
        "/v1/embeddings",
        headers={"Authorization": "Bearer abc"},
        json={"model": "text-embedding-3-large", "input": "hello"},
    )

    assert response.status_code == 400
    mocked.assert_not_awaited()


def test_missing_model_is_rejected(monkeypatch):
    mocked = AsyncMock(return_value=_upstream_response())
    monkeypatch.setattr(proxy, "_send_upstream", mocked)

    response = client.post(
        "/v1/embeddings",
        headers={"Authorization": "Bearer abc"},
        json={"input": "hello"},
    )

    assert response.status_code == 400
    mocked.assert_not_awaited()


def test_other_endpoint_is_not_available():
    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer abc"},
        json={"model": "gpt-5", "messages": []},
    )
    assert response.status_code == 404


def test_docs_and_openapi_are_not_available():
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_wrong_http_method_is_rejected():
    response = client.get(
        "/v1/embeddings",
        headers={"Authorization": "Bearer abc"},
    )
    assert response.status_code == 405


def test_upstream_status_and_body_are_relayed(monkeypatch):
    payload = {"error": {"message": "upstream rejected request"}}
    monkeypatch.setattr(
        proxy,
        "_send_upstream",
        AsyncMock(return_value=_upstream_response(status_code=429, payload=payload)),
    )

    response = client.post(
        "/v1/embeddings",
        headers={"Authorization": "Bearer any-key"},
        json={"model": proxy.ALLOWED_MODEL, "input": "hello"},
    )

    assert response.status_code == 429
    assert response.json() == payload

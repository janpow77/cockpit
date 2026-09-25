"""Regression: HTTP 429 darf nicht als Router-Ausfall oder Modellverlust gelten."""

import httpx
import pytest

from cockpit.services import ai_router_client as client
from cockpit.services.wall_extras import handlungsbedarf

TAGS = {"models": [{"name": "qwen3:8b", "size": 123, "details": {"family": "qwen3"}}]}


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(client, "_cache", {})
    monkeypatch.setattr(client, "_resolved", {})
    for key in ("AI_ROUTER_URL", "AI_ROUTER_APP_ID", "AI_ROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def transport(monkeypatch):
    real_client = httpx.Client

    def install(handler):
        monkeypatch.setattr(client.httpx, "Client", lambda **kwargs: real_client(
            transport=httpx.MockTransport(handler), **kwargs,
        ))

    return install


def test_model_requests_use_own_app_and_cache(transport, monkeypatch):
    seen = []
    monkeypatch.setenv("AI_ROUTER_API_KEY", "test-key")

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=TAGS)

    transport(handler)
    assert client.status()["ok"]
    assert client.list_models()[0]["name"] == "qwen3:8b"
    assert len(seen) == 1
    assert seen[0].headers["x-app-id"] == "cockpit"
    assert seen[0].headers["x-api-key"] == "test-key"


def test_429_does_not_try_unreachable_fallback(transport):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(429, headers={"Retry-After": "17"})

    transport(handler)
    status = client.status()
    assert status["state"] == "overloaded"
    assert not status["ok"] and status["reachable"]
    assert status["retry_after"] == 17
    assert status["url"] == "http://ai-router:7842"
    assert seen == ["http://ai-router:7842/api/tags"]
    alarm = handlungsbedarf([], [], [], [], status, None, [])[0]
    assert "überlastet" in alarm["text"]
    assert "nicht erreichbar" not in alarm["text"]
    assert "ohne Modelle" not in alarm["text"]


def test_stale_models_expire_even_with_cached_error(transport, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(client.time, "monotonic", lambda: clock[0])
    transport(lambda request: httpx.Response(200, json=TAGS))
    assert client.list_models()
    clock[0] += 299
    transport(lambda request: httpx.Response(429, headers={"Retry-After": "30"}))
    stale = client.model_snapshot(refresh=True)
    assert stale["stale"] and stale["models"] and not stale["ok"]
    clock[0] += 2
    expired = client.model_snapshot()
    assert not expired["models"] and not expired["stale"]
    assert expired["state"] == "overloaded"


def test_overload_recovers_after_retry_interval(transport, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(client.time, "monotonic", lambda: clock[0])
    transport(lambda request: httpx.Response(429))
    assert client.status()["state"] == "overloaded"
    transport(lambda request: httpx.Response(200, json=TAGS))
    clock[0] += client.ERROR_TTL_S + 1
    status = client.status()
    assert status["ok"] and status["state"] == "ok" and not status["stale"]


def test_transport_failure_uses_fallback(transport):
    def handler(request):
        if request.url.host == "ai-router":
            raise httpx.ConnectError("DNS failed", request=request)
        return httpx.Response(200, json=TAGS)

    transport(handler)
    status = client.status()
    assert status["ok"] and status["url"] == client.DEFAULT_URL


def test_all_transport_failures_are_unreachable(transport):
    def handler(request):
        raise httpx.ConnectTimeout("timeout", request=request)

    transport(handler)
    status = client.status()
    assert not status["reachable"] and not status["ok"]
    assert status["state"] == "unreachable"


@pytest.mark.parametrize("code,state", [(401, "auth_error"), (403, "auth_error"), (503, "http_error")])
def test_http_errors_are_not_network_failures(transport, code, state):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(code)

    transport(handler)
    status = client.status()
    assert status["reachable"] and status["state"] == state
    assert status["http_status"] == code and len(seen) == 1


def test_empty_success_clears_previous_models(transport):
    transport(lambda request: httpx.Response(200, json=TAGS))
    assert client.list_models()
    transport(lambda request: httpx.Response(200, json={"models": []}))
    status = client.model_snapshot(refresh=True)
    assert status["state"] == "empty" and status["reachable"]
    assert not status["models"] and not status["stale"]


def test_invalid_response_is_not_an_outage(transport):
    transport(lambda request: httpx.Response(200, json={"wrong": []}))
    status = client.status()
    assert status["reachable"] and status["state"] == "invalid_response"


@pytest.mark.asyncio
async def test_chat_uses_same_app_credentials(monkeypatch):
    seen = []
    monkeypatch.setenv("AI_ROUTER_APP_ID", "cockpit")
    monkeypatch.setenv("AI_ROUTER_API_KEY", "test-key")
    real_client = httpx.AsyncClient

    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=b'{"message":{"content":"ok"},"done":true}\n')

    monkeypatch.setattr(client.httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs,
    ))
    chunks = [chunk async for chunk in client.chat_stream("qwen3:8b", [])]
    assert chunks[0]["delta"] == "ok" and chunks[-1]["done"]
    assert seen[0].headers["x-app-id"] == "cockpit"
    assert seen[0].headers["x-api-key"] == "test-key"

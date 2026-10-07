"""The shared LLM routes (agents/llm_routes.py) behind watchlist discovery and the SWOT Analyst,
ported from the prototype's tests: rate-limit waits, the plain-JSON retry when a provider rejects
its own schema output, and falling back to the next route. No network: an httpx.MockTransport
answers, and sleeps are recorded instead of taken."""
from __future__ import annotations

import json

import httpx
import pytest

from agents.llm_routes import AZURE_MAX_TOKENS, Drafter, LLMError

MSG = [{"role": "user", "content": "hi"}]
SCHEMA = {"type": "object"}


def drafter(settings, handler, azure=False):
    settings.groq_api_key, settings.nvidia_api_key = "g-key", "n-key"
    settings.llm_routes = "groq:openai/gpt-oss-120b,nvidia:nvidia/nemotron"
    if azure:
        settings.azure_openai_endpoint, settings.azure_openai_api_key = "https://x.example.com/", "a-key"
        settings.azure_openai_deployment = "mini"
    waits = []
    return Drafter(transport=httpx.MockTransport(handler), sleep=waits.append), waits


def ok(content):
    return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": content}}]})


def test_waits_out_a_rate_limit_then_uses_groq_at_low_effort(settings):
    calls = []

    def handler(req):
        calls.append(json.loads(req.content))
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "7"}, json={"error": {"message": "rate limited"}})
        return ok("```json\n" + json.dumps({"ok": True}) + "\n```")

    d, waits = drafter(settings, handler)
    assert json.loads(d.draft("sys", MSG, SCHEMA)) == {"ok": True}
    assert waits == [8.0] and d.model == "groq:openai/gpt-oss-120b"
    assert calls[1]["reasoning_effort"] == "low" and calls[1]["max_completion_tokens"] > 0
    assert calls[1]["model"] == "openai/gpt-oss-120b" and calls[1]["response_format"]["type"] == "json_schema"


def test_a_rate_limit_longer_than_the_cap_moves_to_the_next_route(settings):
    hosts = []

    def handler(req):
        hosts.append(req.url.host)
        if req.url.host == "api.groq.com":
            return httpx.Response(429, headers={"retry-after": "600"})
        return ok(json.dumps({"ok": True}))

    d, waits = drafter(settings, handler)
    d.draft("sys", MSG, SCHEMA)
    assert hosts == ["api.groq.com", "integrate.api.nvidia.com"] and waits == []


def test_retries_in_plain_json_when_the_provider_rejects_its_schema_output(settings):
    calls = []

    def handler(req):
        body = json.loads(req.content)
        calls.append(body)
        if body["response_format"]["type"] == "json_schema":
            return httpx.Response(400, json={"error": {"message": "Generated JSON does not match the expected schema."}})
        return ok(json.dumps({"ok": 1}))

    d, _ = drafter(settings, handler)
    assert json.loads(d.draft("sys", MSG, SCHEMA)) == {"ok": 1}
    assert len(calls) == 2 and calls[1]["response_format"] == {"type": "json_object"}
    assert "JSON Schema" in calls[1]["messages"][0]["content"]


def test_falls_back_to_nvidia_when_the_groq_request_is_too_large(settings):
    seen = []

    def handler(req):
        body = json.loads(req.content)
        seen.append((req.url.host, body["model"]))
        if req.url.host == "api.groq.com":
            return httpx.Response(413, json={"error": {"message": "Request too large"}})
        assert req.headers["authorization"] == "Bearer n-key" and body["max_tokens"] > 0 and "reasoning_effort" not in body
        return ok(json.dumps({"ok": True}))

    d, _ = drafter(settings, handler)
    d.draft("sys", MSG, SCHEMA)
    assert seen == [("api.groq.com", "openai/gpt-oss-120b"), ("integrate.api.nvidia.com", "nvidia/nemotron")]
    assert d.model == "nvidia:nvidia/nemotron"


def test_azure_is_the_last_route(settings):
    def handler(req):
        if req.url.host == "api.groq.com":
            return httpx.Response(401)
        if req.url.host == "integrate.api.nvidia.com":
            return httpx.Response(404)
        body = json.loads(req.content)
        assert "/openai/deployments/mini/chat/completions" in str(req.url) and req.headers["api-key"] == "a-key"
        assert "model" not in body and body["max_tokens"] == AZURE_MAX_TOKENS
        return ok("<think>reasoning</think>" + json.dumps({"ok": True}))

    d, _ = drafter(settings, handler, azure=True)
    assert json.loads(d.draft("sys", MSG, SCHEMA)) == {"ok": True} and d.model == "azure:mini"


def test_reports_every_route_that_failed(settings):
    d, waits = drafter(settings, lambda req: httpx.Response(503, json={"error": {"message": "overloaded"}}))
    with pytest.raises(LLMError, match="groq:openai/gpt-oss-120b: HTTP 503.*nvidia:nvidia/nemotron: HTTP 503"):
        d.draft("sys", MSG, SCHEMA)
    assert waits == [3, 10, 3, 10], "server errors retry briefly on each route"


def test_a_reply_cut_off_for_length_moves_on(settings):
    def handler(req):
        if req.url.host == "api.groq.com":
            return httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": "{"}}]})
        return ok(json.dumps({"ok": True}))

    d, _ = drafter(settings, handler)
    d.draft("sys", MSG, SCHEMA)
    assert d.model == "nvidia:nvidia/nemotron"


def test_misconfigured_routes_are_refused(settings):
    settings.groq_api_key = "g-key"
    settings.llm_routes = "openai:gpt-5"
    with pytest.raises(LLMError, match="Bad LLM_ROUTES entry"):
        Drafter()
    settings.llm_routes = "groq:openai/gpt-oss-120b"
    settings.groq_api_key = ""
    with pytest.raises(LLMError, match="No LLM is configured"):
        Drafter()

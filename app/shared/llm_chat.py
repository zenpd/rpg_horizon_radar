"""Schema-constrained JSON drafts from a reasoning model, for watchlist
discovery (services/discovery.py) and SWOT briefs (services/swot.py). Never
used for scoring — services/scoring.py stays rule-based.

Routes are tried in order (``LLM_ROUTES``, default Groq gpt-oss-120b at low
reasoning effort, then NVIDIA Nemotron 3 Super); Azure OpenAI
(``AZURE_OPENAI_*``, e.g. gpt-4.1-mini) is the last route when configured.
Per route:
- 429: wait as long as the provider asks (up to MAX_WAIT), then retry.
- 5xx or a dropped connection: retry briefly, then move on.
- 404/410 (retired or not enabled), 413 (too large for the plan), timeout: move on.
- The provider rejects its own schema-constrained output: ask once more in
  plain JSON mode with the schema in the prompt. Callers validate the result.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

import httpx

from shared.config import get_settings
from shared.http import client

PROVIDERS = {
    "groq": {"url": "https://api.groq.com/openai/v1/chat/completions", "key": "groq_api_key", "max_field": "max_completion_tokens"},
    "nvidia": {"url": "https://integrate.api.nvidia.com/v1/chat/completions", "key": "nvidia_api_key", "max_field": "max_tokens"},
}
MAX_TOKENS = 24000  # reasoning plus the JSON; Nemotron reasons ~8k tokens first
AZURE_MAX_TOKENS = 4000
MAX_WAIT = 65  # longest rate-limit wait accepted, in seconds
MAX_RATE_WAITS = 4  # rate-limit waits per route before moving on
RETRY_WAITS = [0, 3, 10]  # before each attempt on the same route


class LLMError(Exception):
    pass


@dataclass
class Route:
    provider: str  # groq | nvidia | azure
    model: str
    url: str
    headers: dict
    max_field: str
    max_tokens: int
    extra: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return f"{self.provider}:{self.model}"


def routes_from_settings() -> list[Route]:
    s = get_settings()
    out = []
    for item in s.llm_routes.split(","):
        provider, _, model = item.strip().partition(":")
        if not item.strip():
            continue
        if provider not in PROVIDERS or not model:
            raise LLMError(f"Bad LLM_ROUTES entry '{item}'. Use provider:model with provider one of {', '.join(PROVIDERS)}.")
        p = PROVIDERS[provider]
        key = getattr(s, p["key"])
        if key:
            # gpt-oss thinks less at low effort: about a third of the output
            # tokens, which keeps a draft and a revision inside Groq's free
            # tier of 8,000 tokens a minute.
            extra = {"reasoning_effort": s.llm_reasoning_effort} if "gpt-oss" in model else {}
            out.append(Route(provider, model, p["url"], {"Authorization": f"Bearer {key}"}, p["max_field"], MAX_TOKENS, extra))
    if s.azure_openai_endpoint and s.azure_openai_api_key and s.azure_openai_deployment:
        base = s.azure_openai_endpoint.split("/openai")[0].rstrip("/")
        url = f"{base}/openai/deployments/{s.azure_openai_deployment}/chat/completions?api-version={s.azure_openai_api_version}"
        out.append(Route("azure", s.azure_openai_deployment, url, {"api-key": s.azure_openai_api_key}, "max_tokens", AZURE_MAX_TOKENS))
    return out


class Drafter:
    """Holds the routes; ``model`` names the route that served the last draft."""

    def __init__(self, routes: list[Route] | None = None, transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        self.routes = routes if routes is not None else routes_from_settings()
        if not self.routes:
            raise LLMError("No LLM is configured. Set GROQ_API_KEY, NVIDIA_API_KEY or the AZURE_OPENAI_* settings.")
        self.model = self.routes[0].name
        self.sleep = sleep
        self.http = client(transport, timeout=300.0)

    def draft(self, system: str, messages: list[dict], schema: dict, name: str = "draft") -> str:
        """One JSON draft as text. ``messages`` may carry earlier drafts and feedback for a revision."""
        tried: list[str] = []
        for route in self.routes:
            text = self._route(route, system, messages, schema, name, tried)
            if text is not None:
                self.model = route.name
                return text
        raise LLMError("No model could take the request (" + "; ".join(tried) + ").")

    def close(self) -> None:
        self.http.close()

    def _route(self, route: Route, system: str, messages: list[dict], schema: dict, name: str, tried: list[str]) -> str | None:
        strict = {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}}
        loose_system = system + "\n\nReturn only one JSON object that matches this JSON Schema:\n" + json.dumps(schema)
        body = {"temperature": 0.2, route.max_field: route.max_tokens, **route.extra,
                "messages": [{"role": "system", "content": system}, *messages], "response_format": strict}
        if route.provider != "azure":
            body["model"] = route.model
        attempts, waits, loose = 0, 0, False
        while attempts < len(RETRY_WAITS):
            if RETRY_WAITS[attempts]:
                self.sleep(RETRY_WAITS[attempts])
            try:
                r = self.http.post(route.url, headers=route.headers, json=body)
            except httpx.TimeoutException:
                tried.append(f"{route.name}: timed out")
                return None
            except (httpx.RemoteProtocolError, httpx.ReadError):
                tried.append(f"{route.name}: connection dropped")
                attempts += 1
                continue
            except httpx.ConnectError as e:
                tried.append(f"{route.name}: unreachable ({e})")
                return None
            status = r.status_code
            if status == 429:
                wait = _retry_after(r)
                waits += 1
                if wait > MAX_WAIT or waits > MAX_RATE_WAITS:
                    tried.append(f"{route.name}: rate limited")
                    return None
                self.sleep(wait)
                continue
            if status in (401, 403):
                tried.append(f"{route.name}: key rejected or access denied (HTTP {status})")
                return None
            if status in (404, 410, 413):
                tried.append(f"{route.name}: HTTP {status}")
                return None
            if status >= 500:
                tried.append(f"{route.name}: HTTP {status}")
                attempts += 1
                continue
            if status == 400 and not loose and _schema_rejected(r):
                loose = True
                body = {**body, "response_format": {"type": "json_object"},
                        "messages": [{"role": "system", "content": loose_system}, *messages]}
                continue
            if status != 200:
                tried.append(f"{route.name}: HTTP {status} {r.text[:120]}")
                return None
            try:
                choice = r.json()["choices"][0]
            except (ValueError, KeyError, IndexError):
                tried.append(f"{route.name}: reply without choices")
                return None
            if choice.get("finish_reason") == "length":
                tried.append(f"{route.name}: ran out of output tokens")
                return None
            return _json_text(choice.get("message", {}).get("content") or "")
        return None


def _retry_after(r: httpx.Response) -> float:
    try:
        return float(r.headers.get("retry-after", "")) + 1
    except ValueError:
        m = re.search(r"try again in ([\d.]+)s", r.text)
        return float(m.group(1)) + 1 if m else 20.0


def _schema_rejected(r: httpx.Response) -> bool:
    t = r.text.lower()
    return "json" in t and ("validate" in t or "generate" in t or "schema" in t)


def _json_text(content: str) -> str:
    """Strip reasoning tags or code fences some models wrap around the JSON."""
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
    if fenced:
        content = fenced.group(1)
    try:
        json.loads(content)
        return content
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.DOTALL)
        return m.group(0) if m else content

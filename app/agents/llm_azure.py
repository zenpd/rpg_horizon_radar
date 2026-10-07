"""Azure OpenAI (a small chat deployment such as gpt-4.1-mini) for the short LLM steps: turning a
thesis into criteria, and answering Ask Radar questions the keyword rules cannot match.
Reasoning-heavy work (the SWOT Analyst) does not use this.

Settings come from the repo's settings (app/.env or Key Vault): AZURE_OPENAI_ENDPOINT,
AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT, AZURE_OPENAI_API_VERSION. Every caller has a
rule-based fallback, so the app behaves as before when Azure is not configured or not reachable.
TLS is always verified, against the OS certificate store (truststore)."""
from __future__ import annotations

import json
import ssl
import time

import httpx
import truststore

from shared.config import get_settings

COOLDOWN = 300  # seconds to skip Azure after a failure, so the fallback answers without a wait


class AzureError(Exception):
    pass


class AzureChat:
    def __init__(self, transport: httpx.BaseTransport | None = None):
        self.transport = transport
        self._http: httpx.Client | None = None
        self.down_until = 0.0
        self.last_error: str | None = None

    # Read at call time, so tests can change the settings.
    endpoint = property(lambda self: get_settings().azure_openai_endpoint.split("/openai")[0].rstrip("/"))
    key = property(lambda self: get_settings().azure_openai_api_key)
    deployment = property(lambda self: get_settings().azure_openai_deployment if get_settings().azure_openai_endpoint else "")
    version = property(lambda self: get_settings().azure_openai_api_version)

    @property
    def configured(self) -> bool:
        return bool(self.endpoint and self.key and self.deployment)

    @property
    def available(self) -> bool:
        return self.configured and time.monotonic() >= self.down_until

    def _client(self) -> httpx.Client:
        if self._http is None:
            verify = True if self.transport else truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            self._http = httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0), verify=verify, transport=self.transport)
        return self._http

    def complete_json(self, system: str, user: str, schema: dict, name: str, max_tokens: int = 800) -> dict:
        """One schema-constrained reply as a dict. Raises AzureError; after a failure Azure is skipped for COOLDOWN seconds."""
        if not self.available:
            raise AzureError(self.last_error or "Azure OpenAI is not configured.")
        url = f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions?api-version={self.version}"
        body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": 0, "max_tokens": max_tokens,
                "response_format": {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}}}
        try:
            r = self._client().post(url, headers={"api-key": self.key}, json=body)
        except httpx.HTTPError as ex:
            raise self._fail(f"Could not reach Azure OpenAI: {type(ex).__name__}")
        if r.status_code != 200:
            try:
                msg = r.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                msg = r.text[:200]
            raise self._fail(f"Azure OpenAI error {r.status_code}: {msg}")
        choice = r.json()["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise AzureError(f"Azure OpenAI stopped early ({choice.get('finish_reason')}).")
        try:
            return json.loads(choice["message"]["content"])
        except (json.JSONDecodeError, KeyError, TypeError):
            raise AzureError("Azure OpenAI returned something that is not JSON.")

    def _fail(self, msg: str) -> AzureError:
        self.last_error, self.down_until = msg, time.monotonic() + COOLDOWN
        return AzureError(msg)


AZURE = AzureChat()

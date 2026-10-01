"""Outbound HTTP for live connectors and LLM routes.

TLS is always verified, against the OS certificate store (truststore), so a
corporate proxy that re-signs HTTPS works without turning verification off.
Tests pass an ``httpx.MockTransport`` instead."""
from __future__ import annotations

import ssl

import httpx
import truststore


def client(transport: httpx.BaseTransport | None = None, timeout: float = 30.0) -> httpx.Client:
    verify = True if transport else truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    return httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0), verify=verify, transport=transport)

"""The SWOT Analyst's drafter, on the repo's shared LLM routes (shared/llm_chat.py:
Groq gpt-oss-120b at low effort, then NVIDIA Nemotron, then Azure OpenAI). Keeps
the prototype's interface: draft() returns (JSON text, the assistant message to
append before a revision)."""
from __future__ import annotations

from shared.llm_chat import Drafter, LLMError

ChatError = LLMError


class ChatDrafter:
    def __init__(self, drafter: Drafter | None = None):
        self.inner = drafter or Drafter()

    @property
    def model(self) -> str:
        return self.inner.model

    def draft(self, system: str, messages: list[dict], schema: dict) -> tuple[str, dict]:
        text = self.inner.draft(system, messages, schema, "swot")
        return text, {"role": "assistant", "content": text}

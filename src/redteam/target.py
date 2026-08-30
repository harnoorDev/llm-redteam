"""OpenAI-compatible chat target adapter (works with Ollama, LM Studio, vLLM, etc.)."""
from __future__ import annotations

import re

import httpx


class TargetError(RuntimeError):
    """Raised when the target model cannot be reached or errors out."""


class OpenAICompatTarget:
    """Minimal client for any OpenAI-compatible /v1/chat/completions endpoint."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        timeout_s: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout_s,
        )

    def _strip_think(self, text: str) -> str:
        # Reasoning models wrap scratch work in <think>...</think>; judge the visible answer.
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    def send_history(self, messages: list[dict]) -> str:
        """Send a full message history; returns assistant text."""
        payload_msgs = list(messages)
        if self.system_prompt:
            payload_msgs = [{"role": "system", "content": self.system_prompt}] + payload_msgs
        try:
            resp = self._client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": payload_msgs,
                    "temperature": self.temperature,
                },
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise TargetError(f"HTTP {e.response.status_code}: {e.response.text[:300]}") from e
        except httpx.HTTPError as e:
            raise TargetError(f"connection failed: {e}") from e
        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise TargetError(f"malformed response: {e}") from e
        return self._strip_think(content or "")

    def send(self, user_text: str) -> str:
        """One-shot single-user-turn convenience wrapper."""
        return self.send_history([{"role": "user", "content": user_text}])

    def close(self) -> None:
        self._client.close()
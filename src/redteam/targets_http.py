"""Raw-HTTP targets — attack an application, not just a model endpoint.

`OpenAICompatTarget` only speaks to OpenAI-shaped `/chat/completions` APIs.
Most real deployments are not that: they are a product's own chat endpoint
behind session cookies, CSRF headers, and a bespoke JSON envelope.

`RawHTTPTarget` takes a raw HTTP request — the kind you copy straight out of
Burp or a browser's "copy as cURL" — with a `{PROMPT}` placeholder where the
user's message goes:

    POST /api/v1/chat HTTP/1.1
    Host: app.internal
    Content-Type: application/json
    Cookie: session=abc123

    {"message": "{PROMPT}", "conversation_id": "42"}

That covers essentially any HTTP-reachable target without writing an adapter.

Both targets satisfy the same contract the runner expects: `send(text)`,
`send_history(messages)`, `close()`.
"""
from __future__ import annotations

import json
import logging
import re

import httpx

from redteam.target import TargetError

log = logging.getLogger(__name__)

PROMPT_TOKEN = "{PROMPT}"  # noqa: S105 - a placeholder, not a secret


def _json_escape(text: str) -> str:
    """Escape a prompt for insertion inside a JSON string literal.

    Attack payloads are full of quotes, backslashes and newlines. Substituting
    one into a JSON body raw produces malformed JSON and the target 400s —
    which looks like a robust model but is really a broken request.
    """
    return json.dumps(text)[1:-1]


class RawHTTPTarget:
    """Send prompts by filling {PROMPT} into a raw HTTP request."""

    def __init__(self, raw_request: str, base_url: str = "",
                 response_path: str | None = None,
                 response_regex: str | None = None,
                 timeout_s: float = 60.0, verify: bool = True,
                 follow_redirects: bool = True):
        """
        raw_request    : the full request, headers and body, with {PROMPT}
        base_url       : scheme+host when the request line is a bare path
        response_path  : dot path into a JSON reply, e.g. "data.reply.text";
                         list indices allowed: "choices.0.message.content"
        response_regex : alternative extraction, first capture group wins
        """
        if PROMPT_TOKEN not in raw_request:
            raise ValueError(
                f"raw_request must contain the {PROMPT_TOKEN} placeholder")
        self.raw_request = raw_request
        self.base_url = base_url.rstrip("/")
        self.response_path = response_path
        self.response_regex = response_regex
        self._client = httpx.Client(timeout=timeout_s, verify=verify,
                                    follow_redirects=follow_redirects)

    # ---- request parsing --------------------------------------------------

    @staticmethod
    def _parse(raw: str) -> tuple[str, str, dict, str]:
        """Split a raw HTTP request into (method, path, headers, body)."""
        raw = raw.replace("\r\n", "\n").lstrip("\n")
        head, _, body = raw.partition("\n\n")
        lines = [ln for ln in head.split("\n") if ln.strip()]
        if not lines:
            raise ValueError("empty raw_request")
        parts = lines[0].split()
        if len(parts) < 2:
            raise ValueError(f"malformed request line: {lines[0]!r}")
        method, path = parts[0].upper(), parts[1]
        headers: dict[str, str] = {}
        for ln in lines[1:]:
            k, sep, v = ln.partition(":")
            if sep:
                headers[k.strip()] = v.strip()
        return method, path, headers, body

    def _url(self, path: str, headers: dict) -> str:
        if path.startswith(("http://", "https://")):
            return path
        if self.base_url:
            return f"{self.base_url}{path}"
        host = headers.get("Host") or headers.get("host")
        if not host:
            raise ValueError(
                "cannot build a URL: give base_url, or a Host header, "
                "or an absolute request line")
        return f"https://{host}{path}"

    # ---- response extraction ----------------------------------------------

    def _extract(self, resp: httpx.Response) -> str:
        text = resp.text
        if self.response_regex:
            m = re.search(self.response_regex, text, re.DOTALL)
            if not m:
                raise TargetError(
                    f"response_regex did not match (HTTP {resp.status_code})")
            return (m.group(1) if m.groups() else m.group(0)).strip()
        if self.response_path:
            try:
                node = resp.json()
            except ValueError as e:
                raise TargetError(
                    f"response was not JSON (HTTP {resp.status_code})") from e
            for part in self.response_path.split("."):
                node = node[int(part)] if isinstance(node, list) else node[part]
            return node if isinstance(node, str) else json.dumps(node)
        # No extractor configured: JSON bodies usually carry the reply in one
        # of a few conventional places, so try those before falling back.
        try:
            data = resp.json()
        except ValueError:
            return text.strip()
        for path in (("choices", 0, "message", "content"),
                     ("message",), ("reply",), ("response",),
                     ("output",), ("text",), ("content",), ("answer",)):
            node = data
            try:
                for p in path:
                    node = node[p]
                if isinstance(node, str):
                    return node.strip()
            except (KeyError, IndexError, TypeError):
                continue
        return text.strip()

    # ---- the runner-facing contract ---------------------------------------

    def send(self, user_text: str) -> str:
        method, path, headers, body = self._parse(self.raw_request)
        in_json = "json" in (headers.get("Content-Type")
                             or headers.get("content-type") or "").lower()
        filled = _json_escape(user_text) if in_json else user_text
        path = path.replace(PROMPT_TOKEN, filled)
        body = body.replace(PROMPT_TOKEN, filled)
        headers = {k: v.replace(PROMPT_TOKEN, filled)
                   for k, v in headers.items()}
        # httpx sets these itself; a stale copied value corrupts the request
        headers.pop("Content-Length", None)
        headers.pop("content-length", None)

        url = self._url(path, headers)
        try:
            resp = self._client.request(
                method, url, headers=headers,
                content=body.encode() if body else None)
        except httpx.HTTPError as e:
            raise TargetError(f"{type(e).__name__}: {e}") from e
        if resp.status_code >= 400:
            raise TargetError(
                f"HTTP {resp.status_code}: {resp.text[:200]}")
        return self._extract(resp)

    def send_history(self, messages: list[dict]) -> str:
        """Flatten a conversation into one prompt.

        A raw endpoint has no shared notion of chat history, so multi-turn
        strategies are rendered as a labelled transcript. Targets that keep
        server-side session state will still thread the conversation via
        whatever cookie or id the raw request carries.
        """
        if not messages:
            return self.send("")
        if len(messages) == 1:
            return self.send(_content_text(messages[0]))
        lines = []
        for m in messages:
            role = (m.get("role") or "user").capitalize()
            lines.append(f"{role}: {_content_text(m)}")
        return self.send("\n".join(lines))

    def close(self) -> None:
        self._client.close()


def _content_text(message: dict) -> str:
    """Message content may be a string or a list of typed blocks."""
    from redteam.runner import flatten_content
    return flatten_content(message.get("content", ""))

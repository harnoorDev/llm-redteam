"""RawHTTPTarget: attack any HTTP app, not just OpenAI-shaped endpoints."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest

from redteam.target import TargetError
from redteam.targets_http import RawHTTPTarget

RAW = """POST /api/chat HTTP/1.1
Host: 127.0.0.1
Content-Type: application/json
X-Session: abc123

{"message": "{PROMPT}", "conversation_id": "42"}"""


class _Handler(BaseHTTPRequestHandler):
    received: ClassVar[list] = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode()
        _Handler.received.append({"path": self.path, "body": raw,
                                  "headers": dict(self.headers)})
        if self.path.startswith("/broken"):
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"kaboom")
            return
        try:
            sent = json.loads(raw)["message"]
        except (ValueError, KeyError):
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error":"bad json"}')
            return
        body = json.dumps({"data": {"reply": {"text": f"echo: {sent}"}}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture(autouse=True)
def _clear():
    _Handler.received.clear()


def test_requires_the_prompt_placeholder():
    with pytest.raises(ValueError, match="PROMPT"):
        RawHTTPTarget("POST /x HTTP/1.1\nHost: h\n\n{}")


def test_parses_a_raw_request_into_parts():
    method, path, headers, body = RawHTTPTarget._parse(RAW)
    assert method == "POST"
    assert path == "/api/chat"
    assert headers["Content-Type"] == "application/json"
    assert headers["X-Session"] == "abc123"
    assert "{PROMPT}" in body


def test_sends_and_extracts_via_json_path(server):
    t = RawHTTPTarget(RAW, base_url=server, response_path="data.reply.text")
    assert t.send("hello") == "echo: hello"
    t.close()


def test_custom_headers_survive_to_the_wire(server):
    t = RawHTTPTarget(RAW, base_url=server, response_path="data.reply.text")
    t.send("hi")
    assert _Handler.received[0]["headers"]["X-Session"] == "abc123"
    t.close()


def test_json_bodies_are_escaped_so_payloads_do_not_break_the_request(server):
    """Attack payloads are full of quotes and newlines — the whole point."""
    t = RawHTTPTarget(RAW, base_url=server, response_path="data.reply.text")
    nasty = 'He said "hello"\nthen \\ escaped {"json": true}'
    out = t.send(nasty)
    # the server round-trips it, which proves the JSON stayed well-formed
    assert out == f"echo: {nasty}"
    assert json.loads(_Handler.received[0]["body"])["message"] == nasty
    t.close()


def test_stale_content_length_is_dropped(server):
    raw = RAW.replace("X-Session: abc123",
                      "X-Session: abc123\nContent-Length: 9999")
    t = RawHTTPTarget(raw, base_url=server, response_path="data.reply.text")
    assert t.send("hello") == "echo: hello"   # would hang or 400 if kept
    t.close()


def test_regex_extraction(server):
    t = RawHTTPTarget(RAW, base_url=server,
                      response_regex=r'"text":\s*"([^"]+)"')
    assert t.send("abc") == "echo: abc"
    t.close()


def test_extractor_autodetects_common_envelopes(server):
    t = RawHTTPTarget(RAW, base_url=server)   # no path, no regex
    # server nests under data.reply.text, which is not a known envelope, so
    # the raw body comes back — still usable, never an exception
    out = t.send("xyz")
    assert "echo: xyz" in out
    t.close()


def test_http_error_becomes_a_target_error(server):
    raw = RAW.replace("/api/chat", "/broken")
    t = RawHTTPTarget(raw, base_url=server)
    with pytest.raises(TargetError, match="HTTP 500"):
        t.send("hello")
    t.close()


def test_bad_json_path_raises_target_error(server):
    t = RawHTTPTarget(RAW, base_url=server, response_path="nope.missing")
    with pytest.raises((TargetError, KeyError)):
        t.send("hello")
    t.close()


def test_send_history_flattens_a_conversation(server):
    t = RawHTTPTarget(RAW, base_url=server, response_path="data.reply.text")
    out = t.send_history([
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "second"},
    ])
    assert "User: first" in out and "Assistant: reply" in out
    t.close()


def test_single_message_history_is_sent_bare(server):
    t = RawHTTPTarget(RAW, base_url=server, response_path="data.reply.text")
    assert t.send_history([{"role": "user", "content": "solo"}]) == "echo: solo"
    t.close()


def test_url_falls_back_to_the_host_header():
    t = RawHTTPTarget(RAW)
    _, path, headers, _ = RawHTTPTarget._parse(RAW)
    assert t._url(path, headers) == "https://127.0.0.1/api/chat"
    t.close()


def test_url_requires_something_to_go_on():
    raw = "POST /x HTTP/1.1\nAccept: */*\n\n{PROMPT}"
    t = RawHTTPTarget(raw)
    with pytest.raises(ValueError, match="cannot build a URL"):
        t._url("/x", {})
    t.close()


def test_it_satisfies_the_runner_target_contract(server):
    """The runner only needs send / send_history / close."""
    from redteam.runner import Runner

    t = RawHTTPTarget(RAW, base_url=server, response_path="data.reply.text")
    r = Runner(t).run_strategy("say hello", "direct")
    assert r.target_replies and "echo:" in r.target_replies[0]
    assert r.error is None
    t.close()

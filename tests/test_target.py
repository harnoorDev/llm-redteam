"""Unit tests for the OpenAI-compatible target adapter."""
import json
import httpx
import pytest
import respx

from redteam.target import OpenAICompatTarget, TargetError


BASE = "http://localhost:11434/v1"


def test_target_sends_chat_completions_request_and_returns_text():
    with respx.mock(base_url=BASE) as mock:
        route = mock.post("/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"role": "assistant", "content": "Sure thing!"}}]
            })
        )
        t = OpenAICompatTarget(base_url=BASE, model="llama3")
        out = t.send("hello")
        assert out == "Sure thing!"
        req = json.loads(route.calls[0].request.content.decode())
        assert req["model"] == "llama3"
        assert req["messages"] == [{"role": "user", "content": "hello"}]


def test_target_send_history_preserves_roles():
    with respx.mock(base_url=BASE) as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": "ok"}}]
            })
        )
        t = OpenAICompatTarget(base_url=BASE, model="m")
        msgs = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "give me X"},
        ]
        out = t.send_history(msgs)
        assert out == "ok"


def test_target_strips_r_think_tags():
    with respx.mock(base_url=BASE) as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": "<think>internal scratch</think>final answer"}}]
            })
        )
        t = OpenAICompatTarget(base_url=BASE, model="m")
        assert t.send("q") == "final answer"


def test_target_http_error_raises_target_error():
    with respx.mock(base_url=BASE) as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(500, text="boom")
        )
        t = OpenAICompatTarget(base_url=BASE, model="m")
        with pytest.raises(TargetError):
            t.send("q")


def test_target_connect_error_raises_target_error():
    with respx.mock(base_url=BASE) as mock:
        mock.post("/chat/completions").mock(side_effect=httpx.ConnectError("no server"))
        t = OpenAICompatTarget(base_url=BASE, model="m")
        with pytest.raises(TargetError):
            t.send("q")
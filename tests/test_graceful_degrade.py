"""Graceful degradation: when Ollama is unreachable, surface a clear, actionable error.

The router has one external dependency (Ollama for embeddings). The contract is:
if Ollama is down, do NOT crash with an opaque socket error. Raise RuntimeError
with a message that tells the user how to fix it.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
import requests

from claude_router import ClaudeRouter


@pytest.fixture
def router():
    return ClaudeRouter()


def test_ollama_connection_refused_raises_actionable_error(router):
    with patch("claude_router.router.requests.post", side_effect=requests.ConnectionError("nope")):
        with pytest.raises(RuntimeError) as exc:
            router.route("Evaluate this paper for methodological rigor")
    msg = str(exc.value)
    assert "Ollama" in msg
    assert "ollama serve" in msg


def test_ollama_timeout_raises_runtime_error(router):
    with patch("claude_router.router.requests.post", side_effect=requests.Timeout("slow")):
        with pytest.raises(RuntimeError) as exc:
            router.route("any text")
    assert "timed out" in str(exc.value)


def test_ollama_http_error_raises_runtime_error(router):
    class _Resp:
        def raise_for_status(self):
            raise requests.HTTPError("500 Server Error")

    with patch("claude_router.router.requests.post", return_value=_Resp()):
        with pytest.raises(RuntimeError) as exc:
            router.route("any text")
    assert "Ollama returned an error" in str(exc.value)


def test_ollama_invalid_url_raises_actionable_runtime_error(router):
    with patch(
        "claude_router.router.requests.post",
        side_effect=requests.exceptions.InvalidURL("Invalid URL: no host supplied"),
    ):
        with pytest.raises(RuntimeError) as exc:
            router.route("any text")
    msg = str(exc.value)
    assert "Ollama" in msg
    assert "embedding" in msg
    assert isinstance(exc.value.__cause__, requests.exceptions.InvalidURL)

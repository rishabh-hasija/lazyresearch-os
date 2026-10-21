from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from time import perf_counter, sleep

import pytest

from lazyresearch.application.analysis_models import AIError
from lazyresearch.infrastructure.ai.ollama import OllamaHTTP


@pytest.fixture
def server():
    state = {"status": 200, "body": b'{"ok":true}', "delay": 0, "calls": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            state["calls"] += 1
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(state["status"])
            self.send_header("Content-Length", str(len(state["body"])))
            self.send_header("Location", "/never-follow")
            self.end_headers()
            sleep(state["delay"])
            try:
                self.wfile.write(state["body"])
            except OSError:
                pass

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    try:
        yield OllamaHTTP(f"http://127.0.0.1:{httpd.server_port}"), state
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=2)


def test_real_http_json(server):
    wire, _ = server
    assert wire("/api/chat", {"synthetic": "source"}, 2) == {"ok": True}


@pytest.mark.parametrize("body", [b"not json", b"[]", b"\xff"])
def test_real_http_invalid_response(server, body):
    wire, state = server
    state["body"] = body
    with pytest.raises(AIError, match="INVALID_RESPONSE"):
        wire("/api/chat", {}, 2)


@pytest.mark.parametrize("status", [302, 404, 500])
def test_real_http_unavailable_and_redirect_not_followed(server, status):
    wire, state = server
    state["status"] = status
    with pytest.raises(AIError, match="UNAVAILABLE"):
        wire("/api/chat", {}, 2)
    assert state["calls"] == 1


def test_real_http_total_timeout(server):
    wire, state = server
    state["delay"] = 1
    started = perf_counter()
    with pytest.raises(AIError, match="TIMEOUT"):
        wire("/api/chat", {}, 0.15)
    assert perf_counter() - started < 0.8


@pytest.mark.parametrize(
    "endpoint",
    [
        "file:///model",
        "http://u:p@localhost:1",
        "http://localhost/x",
        "http://localhost/?secret=x",
        "http://localhost/#x",
    ],
)
def test_invalid_endpoint(endpoint):
    with pytest.raises(ValueError):
        OllamaHTTP(endpoint)

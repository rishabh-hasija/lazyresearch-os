"""Loopback server behind an explicit test-only transport mapping."""

import contextlib
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import SplitResult

import pytest

from lazyresearch.application.intake_models import IntakeLimits
from lazyresearch.infrastructure.sources.http import HTTPFetcher, HTTPResponse, PinnedHTTPTransport


class ControlledServer(ThreadingHTTPServer):
    daemon_threads = True
    payload = b"first page"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        with contextlib.suppress(ConnectionError):
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/ok?keep=signed")
                self.end_headers()
                return
            if self.path == "/private":
                self.send_response(302)
                self.send_header("Location", "http://127.0.0.1/private")
                self.end_headers()
                return
            if self.path == "/loop":
                self.send_response(302)
                self.send_header("Location", "/loop")
                self.end_headers()
                return
            if self.path == "/slow":
                time.sleep(0.25)
            if self.path == "/headers":
                for byte in b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n":
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                    time.sleep(0.01)
                return
            if self.path == "/body":
                self.send_response(200)
                self.send_header("Content-Length", "100")
                self.end_headers()
                for _ in range(100):
                    self.wfile.write(b"x")
                    self.wfile.flush()
                    time.sleep(0.01)
                return
            body = b"x" * 1000 if self.path.startswith("/large") else self.server.payload
            self.send_response(404 if self.path == "/missing" else 200)
            self.send_header("Content-Type", "text/plain")
            if self.path != "/large-stream":
                self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


class PublicResolver:
    def resolve(self, host: str, port: int, timeout: float) -> tuple[str, ...]:
        if host in {"public.test", "other.test"}:
            return ("8.8.8.8",)
        return (host,)


class LocalTestTransport:
    """Only the test transport maps a validated public destination to the loopback server."""

    def get(
        self, url: SplitResult, address: str, deadline: float, limits: IntakeLimits
    ) -> HTTPResponse:
        assert address == "8.8.8.8"
        return PinnedHTTPTransport().get(url, "127.0.0.1", deadline, limits)


@pytest.fixture(scope="module")
def server() -> Iterator[ControlledServer]:
    instance = ControlledServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=2)


@pytest.fixture
def controlled_fetcher() -> HTTPFetcher:
    return HTTPFetcher(resolver=PublicResolver(), transport=LocalTestTransport())

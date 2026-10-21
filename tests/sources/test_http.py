import http.client
import time
from dataclasses import replace
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from lazyresearch.application.intake_models import ErrorCode, IntakeLimits, SourceError
from lazyresearch.infrastructure.sources import http as source_http
from lazyresearch.infrastructure.sources.http import HTTPFetcher, HTTPResponse


def test_valid_http_preserves_raw_and_query(server, controlled_fetcher: HTTPFetcher) -> None:
    url = f"http://public.test:{server.server_port}/ok?token=synthetic&x=1"
    result = controlled_fetcher.fetch(url)
    assert result.payload == server.payload
    assert result.final_url == url
    assert result.http_status == 200 and result.content_type == "text/plain"
    assert result.fetched_at.tzinfo is not None


def test_redirect(server, controlled_fetcher: HTTPFetcher) -> None:
    result = controlled_fetcher.fetch(f"http://public.test:{server.server_port}/redirect")
    assert result.final_url.endswith("/ok?keep=signed")


@pytest.mark.parametrize(
    "url,code",
    [
        ("file:///tmp/file", ErrorCode.UNSUPPORTED_SCHEME),
        ("http://user:secret@public.test/x", ErrorCode.INVALID_URL),
        ("http://localhost/x", ErrorCode.PRIVATE_NETWORK_BLOCKED),
        ("http://127.0.0.1/x", ErrorCode.PRIVATE_NETWORK_BLOCKED),
        ("http://10.0.0.1/x", ErrorCode.PRIVATE_NETWORK_BLOCKED),
        ("http://169.254.169.254/", ErrorCode.PRIVATE_NETWORK_BLOCKED),
        ("http://[::1]/", ErrorCode.PRIVATE_NETWORK_BLOCKED),
        ("http://224.0.0.1/", ErrorCode.PRIVATE_NETWORK_BLOCKED),
        ("http://[2002:0a00:0001::]/", ErrorCode.PRIVATE_NETWORK_BLOCKED),
        ("http://public.test:99999/", ErrorCode.INVALID_URL),
        ("http://public.test/\r\nX:a", ErrorCode.INVALID_URL),
    ],
)
def test_unsafe_url_is_blocked(controlled_fetcher: HTTPFetcher, url: str, code: ErrorCode) -> None:
    with pytest.raises(SourceError) as error:
        controlled_fetcher.fetch(url)
    assert error.value.code is code


def test_redirect_to_private_is_blocked(server, controlled_fetcher: HTTPFetcher) -> None:
    with pytest.raises(SourceError) as error:
        controlled_fetcher.fetch(f"http://public.test:{server.server_port}/private")
    assert error.value.code is ErrorCode.PRIVATE_NETWORK_BLOCKED


@pytest.mark.parametrize("path", ["/large", "/large-stream"])
def test_response_size_bound(server, controlled_fetcher: HTTPFetcher, path: str) -> None:
    controlled_fetcher.limits = replace(IntakeLimits(), max_fetch_bytes=20)
    with pytest.raises(SourceError) as error:
        controlled_fetcher.fetch(f"http://public.test:{server.server_port}{path}")
    assert error.value.code is ErrorCode.FETCH_TOO_LARGE


@pytest.mark.parametrize("path", ["/slow", "/headers", "/body"])
def test_total_timeout_including_slow_headers(
    server, controlled_fetcher: HTTPFetcher, path: str
) -> None:
    controlled_fetcher.limits = replace(
        IntakeLimits(), fetch_timeout_seconds=0.07, read_timeout_seconds=0.5
    )
    started = time.monotonic()
    with pytest.raises(SourceError) as error:
        controlled_fetcher.fetch(f"http://public.test:{server.server_port}{path}")
    assert error.value.code is ErrorCode.FETCH_TIMEOUT
    assert time.monotonic() - started < 1


def test_http_failure_has_sanitized_code(server, controlled_fetcher: HTTPFetcher) -> None:
    with pytest.raises(SourceError) as error:
        controlled_fetcher.fetch(f"http://public.test:{server.server_port}/missing")
    assert error.value.code is ErrorCode.HTTP_ERROR
    assert str(error.value) == "HTTP_ERROR"


def test_redirect_limit(server, controlled_fetcher: HTTPFetcher) -> None:
    controlled_fetcher.limits = replace(IntakeLimits(), max_redirects=1)
    with pytest.raises(SourceError):
        controlled_fetcher.fetch(f"http://public.test:{server.server_port}/loop")


def test_all_dns_answers_must_be_public() -> None:
    class MixedResolver:
        def resolve(self, host, port, timeout):
            return ("8.8.8.8", "10.0.0.1")

    class NeverTransport:
        def get(self, *args):
            pytest.fail("unsafe DNS answer must prevent any connection")

    with pytest.raises(SourceError) as error:
        HTTPFetcher(resolver=MixedResolver(), transport=NeverTransport()).fetch(
            "http://public.test"
        )
    assert error.value.code is ErrorCode.PRIVATE_NETWORK_BLOCKED


def test_resolved_address_is_passed_to_transport_without_another_resolution() -> None:
    class OnceResolver:
        calls = 0

        def resolve(self, host, port, timeout):
            self.calls += 1
            assert self.calls == 1
            return ("8.8.8.8",)

    class PinnedTransport:
        def get(self, url, address, deadline, limits):
            assert address == "8.8.8.8" and url.hostname == "public.test"
            return HTTPResponse(200, "text/plain", None, b"safe")

    assert (
        HTTPFetcher(resolver=OnceResolver(), transport=PinnedTransport())
        .fetch("http://public.test")
        .payload
        == b"safe"
    )


def test_deadline_abort_is_timeout_even_with_coarse_monotonic_clock(monkeypatch) -> None:
    class DummySocket:
        def dup(self):
            return self

        def shutdown(self, how):
            pass

        def settimeout(self, timeout):
            pass

        def close(self):
            pass

    class ImmediateTimer:
        def __init__(self, delay, callback):
            self.callback = callback

        def start(self):
            self.callback()  # Timer fired, but the sampled clock still reads the prior tick.

        def cancel(self):
            pass

    class DisconnectedConnection:
        def __init__(self, *args):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            raise http.client.RemoteDisconnected("synthetic deadline shutdown")

        def close(self):
            pass

    monkeypatch.setattr(source_http, "time", SimpleNamespace(monotonic=lambda: 100.0))
    monkeypatch.setattr(source_http.socket, "create_connection", lambda *a, **k: DummySocket())
    monkeypatch.setattr(source_http.threading, "Timer", ImmediateTimer)
    monkeypatch.setattr(source_http.http.client, "HTTPConnection", DisconnectedConnection)
    with pytest.raises(SourceError) as error:
        source_http.PinnedHTTPTransport().get(
            urlsplit("http://public.test/"),
            "8.8.8.8",
            101.0,
            IntakeLimits(),
        )
    assert error.value.code is ErrorCode.FETCH_TIMEOUT

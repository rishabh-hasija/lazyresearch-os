"""SSRF-resistant HTTP: validate all DNS answers, then connect to a pinned IP.

No proxies, automatic redirects, cookies, decompression or browser behavior.
Injected resolver/transport seams are for controlled tests; production defaults
always enforce public addresses and TLS hostname verification.
"""

import http.client
import ipaddress
import socket
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import SplitResult, urljoin, urlsplit

from lazyresearch.application.intake_models import (
    ErrorCode,
    FetchedSource,
    IntakeLimits,
    SourceError,
)


class Resolver(Protocol):
    def resolve(self, host: str, port: int, timeout: float) -> tuple[str, ...]: ...


class SystemResolver:
    def __init__(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="lazyresearch-dns")

    def resolve(self, host: str, port: int, timeout: float) -> tuple[str, ...]:
        task = self._pool.submit(socket.getaddrinfo, host, port, 0, socket.SOCK_STREAM)
        try:
            return tuple(dict.fromkeys(str(answer[4][0]) for answer in task.result(timeout)))
        except FutureTimeout as exc:
            task.cancel()
            raise SourceError(ErrorCode.FETCH_TIMEOUT) from exc
        except OSError as exc:
            raise SourceError(ErrorCode.FETCH_FAILED) from exc


@dataclass(frozen=True, slots=True)
class HTTPResponse:
    status: int
    content_type: str
    location: str | None
    body: bytes


class Transport(Protocol):
    def get(
        self, url: SplitResult, address: str, deadline: float, limits: IntakeLimits
    ) -> HTTPResponse: ...


class PinnedHTTPTransport:
    def get(
        self, url: SplitResult, address: str, deadline: float, limits: IntakeLimits
    ) -> HTTPResponse:
        host = url.hostname
        assert host is not None
        port = url.port or (443 if url.scheme == "https" else 80)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SourceError(ErrorCode.FETCH_TIMEOUT)
        sock: socket.socket | ssl.SSLSocket = socket.create_connection(
            (address, port), timeout=min(limits.connect_timeout_seconds, remaining)
        )
        connection = http.client.HTTPConnection(host, port)
        # HTTPConnection may close its socket wrapper after HTTP/1.0 headers.
        # Keep a duplicate handle solely for the total-deadline shutdown.
        guard = sock.dup()
        response: http.client.HTTPResponse | None = None
        deadline_expired = threading.Event()

        def abort() -> None:
            deadline_expired.set()
            try:
                guard.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        timer = threading.Timer(max(0.001, deadline - time.monotonic()), abort)
        timer.daemon = True
        timer.start()
        try:
            if url.scheme == "https":
                sock.settimeout(
                    min(limits.connect_timeout_seconds, max(0.001, deadline - time.monotonic()))
                )
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
            connection.sock = sock
            sock.settimeout(
                min(limits.read_timeout_seconds, max(0.001, deadline - time.monotonic()))
            )
            netloc = f"[{host}]" if ":" in host else host
            if url.port is not None:
                netloc += f":{port}"
            path = url.path or "/"
            if url.query:
                path += "?" + url.query
            connection.request(
                "GET",
                path,
                headers={
                    "Host": netloc,
                    "User-Agent": "LazyResearchOS/0.1",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            if deadline_expired.is_set():
                raise SourceError(ErrorCode.FETCH_TIMEOUT)
            location = response.getheader("Location")
            content_type = response.getheader("Content-Type", "application/octet-stream")
            if 300 <= response.status < 400:
                return HTTPResponse(response.status, content_type, location, b"")
            if not 200 <= response.status < 300:
                return HTTPResponse(response.status, content_type, None, b"")
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                raise SourceError(ErrorCode.UNSUPPORTED_FILE)
            length = response.getheader("Content-Length")
            if length is not None:
                try:
                    if int(length) < 0:
                        raise ValueError
                    if int(length) > limits.max_fetch_bytes:
                        raise SourceError(ErrorCode.FETCH_TOO_LARGE)
                except ValueError as exc:
                    raise SourceError(ErrorCode.FETCH_FAILED) from exc
            body = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SourceError(ErrorCode.FETCH_TIMEOUT)
                block = response.read1(min(65536, limits.max_fetch_bytes + 1 - len(body)))
                if deadline_expired.is_set():
                    raise SourceError(ErrorCode.FETCH_TIMEOUT)
                if not block:
                    break
                body.extend(block)
                if len(body) > limits.max_fetch_bytes:
                    raise SourceError(ErrorCode.FETCH_TOO_LARGE)
            if length is not None and len(body) != int(length):
                raise SourceError(ErrorCode.FETCH_FAILED)
            return HTTPResponse(response.status, content_type, None, bytes(body))
        except (OSError, http.client.HTTPException) as exc:
            if deadline_expired.is_set():
                raise SourceError(ErrorCode.FETCH_TIMEOUT) from exc
            raise
        finally:
            timer.cancel()
            if response is not None:
                response.close()
            connection.close()
            sock.close()
            guard.close()


class HTTPFetcher:
    def __init__(
        self,
        limits: IntakeLimits = IntakeLimits(),
        *,
        resolver: Resolver | None = None,
        transport: Transport | None = None,
    ) -> None:
        self.limits = limits
        self.resolver = resolver if resolver is not None else SystemResolver()
        self.transport = transport if transport is not None else PinnedHTTPTransport()

    def fetch(self, url: str) -> FetchedSource:
        deadline = time.monotonic() + self.limits.fetch_timeout_seconds
        current = url
        try:
            for _ in range(self.limits.max_redirects + 1):
                parsed = self._validate(current)
                host = parsed.hostname
                assert host is not None
                if host.lower().rstrip(".") == "localhost" or host.lower().rstrip(".").endswith(
                    ".localhost"
                ):
                    raise SourceError(ErrorCode.PRIVATE_NETWORK_BLOCKED)
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                addresses = self.resolver.resolve(
                    host, port, max(0.001, deadline - time.monotonic())
                )
                if not addresses:
                    raise SourceError(ErrorCode.FETCH_FAILED)
                for address in addresses:
                    ip = ipaddress.ip_address(address)
                    if (
                        not ip.is_global
                        or ip.is_multicast
                        or ip.is_reserved
                        or (
                            isinstance(ip, ipaddress.IPv6Address)
                            and (
                                ip.ipv4_mapped is not None
                                or ip.sixtofour is not None
                                or ip.teredo is not None
                            )
                        )
                    ):
                        raise SourceError(ErrorCode.PRIVATE_NETWORK_BLOCKED)
                if time.monotonic() >= deadline:
                    raise SourceError(ErrorCode.FETCH_TIMEOUT)
                response = self.transport.get(parsed, addresses[0], deadline, self.limits)
                if time.monotonic() >= deadline:
                    raise SourceError(ErrorCode.FETCH_TIMEOUT)
                if response.status in {301, 302, 303, 307, 308}:
                    if not response.location:
                        raise SourceError(ErrorCode.FETCH_FAILED)
                    current = urljoin(current, response.location)
                    continue
                if not 200 <= response.status < 300:
                    raise SourceError(ErrorCode.HTTP_ERROR, http_status=response.status)
                if len(response.body) > self.limits.max_fetch_bytes:
                    raise SourceError(ErrorCode.FETCH_TOO_LARGE)
                return FetchedSource(
                    payload=response.body,
                    final_url=current,
                    fetched_at=datetime.now(UTC),
                    http_status=response.status,
                    content_type=response.content_type,
                )
            raise SourceError(ErrorCode.FETCH_FAILED)
        except SourceError:
            raise
        except TimeoutError as exc:
            raise SourceError(ErrorCode.FETCH_TIMEOUT) from exc
        except (OSError, http.client.HTTPException, ValueError, UnicodeError) as exc:
            code = (
                ErrorCode.FETCH_TIMEOUT if time.monotonic() >= deadline else ErrorCode.FETCH_FAILED
            )
            raise SourceError(code) from exc

    @staticmethod
    def _validate(url: str) -> SplitResult:
        try:
            if (
                not url
                or "\\" in url
                or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url)
            ):
                raise SourceError(ErrorCode.INVALID_URL)
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"}:
                raise SourceError(ErrorCode.UNSUPPORTED_SCHEME)
            if (
                not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or "%" in parsed.hostname
            ):
                raise SourceError(ErrorCode.INVALID_URL)
            if parsed.port is not None and not 1 <= parsed.port <= 65535:
                raise SourceError(ErrorCode.INVALID_URL)
            # This slice deliberately rejects non-ASCII URL paths/hosts instead of lossy rewriting.
            url.encode("ascii")
            return parsed
        except (ValueError, UnicodeError) as exc:
            raise SourceError(ErrorCode.INVALID_URL) from exc

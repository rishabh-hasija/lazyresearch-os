"""Ollama HTTP adapter. No SDK objects, payload logs, redirects, or hidden retries."""

import http.client
import json
import socket
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from threading import Event, Timer
from time import perf_counter
from typing import cast
from urllib.parse import urlsplit

from pydantic import ValidationError

from lazyresearch.application.analysis_models import (
    AIError,
    AIResult,
    AnalysisConfig,
    AnalysisOutputSchema,
    AnalysisRequest,
    CallAttempt,
)

Wire = Callable[[str, dict[str, object] | None, float], dict[str, object]]


class OllamaHTTP:
    def __init__(
        self, endpoint: str, *, error_classifier: Callable[[int, bytes], AIError] | None = None
    ) -> None:
        self.error_classifier = error_classifier
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("AI_ENDPOINT must be an HTTP(S) origin without credentials or path")
        self.host, self.port, self.secure = parsed.hostname, parsed.port, parsed.scheme == "https"

    def __call__(
        self, path: str, body: dict[str, object] | None, timeout: float
    ) -> dict[str, object]:
        cls = http.client.HTTPSConnection if self.secure else http.client.HTTPConnection
        connection = cls(self.host, self.port, timeout=timeout)
        expired = Event()
        timer: Timer | None = None
        started = perf_counter()
        try:
            connection.connect()
            assert connection.sock is not None
            handle = connection.sock.dup()

            def abort() -> None:
                expired.set()
                try:
                    handle.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            timer = Timer(max(0.001, timeout - (perf_counter() - started)), abort)
            timer.daemon = True
            timer.start()
            try:
                connection.request(
                    "POST" if body is not None else "GET",
                    path,
                    body=json.dumps(body).encode() if body is not None else None,
                    headers={"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                if response.status != 200:
                    if self.error_classifier is not None:
                        raise self.error_classifier(response.status, response.read(4096))
                    raise AIError("UNAVAILABLE")
                raw = response.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise AIError("INVALID_RESPONSE")
            finally:
                timer.cancel()
                handle.close()
            if expired.is_set():
                raise AIError("TIMEOUT")
            decoded = json.loads(raw)
            if not isinstance(decoded, dict):
                raise AIError("INVALID_RESPONSE")
            return cast(dict[str, object], decoded)
        except TimeoutError as exc:
            raise AIError("TIMEOUT") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise AIError("TIMEOUT" if expired.is_set() else "UNAVAILABLE") from exc
        except (ValueError, UnicodeError) as exc:
            raise AIError("INVALID_RESPONSE") from exc
        finally:
            if timer is not None:
                timer.cancel()
            connection.close()


class OllamaProcessor:
    def __init__(self, endpoint: str, *, wire: Wire | None = None) -> None:
        self.wire = wire if wire is not None else OllamaHTTP(endpoint)

    def metadata(self, model: str) -> tuple[str | None, str | None]:
        """Best-effort actual installed digest/runtime. Missing information remains None."""
        revision = runtime = None
        try:
            version = self.wire("/api/version", None, 5).get("version")
            runtime = version if isinstance(version, str) and version else None
            models = self.wire("/api/tags", None, 5).get("models")
            if isinstance(models, list):
                for item in models:
                    if isinstance(item, dict) and item.get("name") == model:
                        digest = item.get("digest")
                        revision = digest if isinstance(digest, str) and digest else None
        except AIError:
            pass
        return revision, runtime

    def analyze(self, request: AnalysisRequest) -> AIResult:
        config = request.config
        anchor = (
            "E"
            + sha256(
                f"{request.extraction_id}:{request.segment.start}:{request.segment.end}:"
                f"{request.segment.page}".encode()
            ).hexdigest()[:24]
        )
        envelope = {
            "content_id": str(request.content_id),
            "extraction_id": str(request.extraction_id),
            "start": request.segment.start,
            "end": request.segment.end,
            "page": request.segment.page,
            "untrusted_source_text": request.segment.text,
        }
        template = {
            "content_id": str(request.content_id),
            "extraction_id": str(request.extraction_id),
            "start": request.segment.start,
            "end": request.segment.end,
            "page": request.segment.page,
            "quote": request.segment.text,
        }
        envelope["evidence_id"] = anchor
        schema = AnalysisOutputSchema.model_json_schema()
        schema["$defs"]["EvidenceLocatorSchema"] = {"type": "string", "enum": [anchor]}
        attempts: list[CallAttempt] = []
        for repair in (False, True):
            started_at, started = datetime.now(UTC), perf_counter()
            outcome = "OK"
            try:
                if (
                    len(request.segment.text) > config.max_input_chars
                    or len(request.segment.text.encode("utf-8")) > config.input_byte_budget
                ):
                    raise AIError("INVALID_RESPONSE")
                if config.model_revision is not None:
                    revision, runtime = self.metadata(config.model)
                    if revision is None:
                        raise AIError("UNAVAILABLE")
                    if revision != config.model_revision or (
                        config.provider_revision is not None and runtime != config.provider_revision
                    ):
                        raise AIError("MODEL_CHANGED")
                response = self.wire(
                    "/api/chat",
                    {
                        "model": config.model,
                        "stream": False,
                        "think": False,
                        "format": schema,
                        "messages": [
                            {
                                "role": "system",
                                "content": config.prompt
                                + (
                                    "\nPrevious output failed the schema. Produce fresh valid JSON "
                                    "with all required fields, correct types and no extra fields."
                                    " If actions is empty, use no_action "
                                    "or insufficient_information; "
                                    "action_required requires a source-supported action."
                                    if repair
                                    else ""
                                ),
                            },
                            {"role": "user", "content": json.dumps(envelope, ensure_ascii=False)},
                        ],
                        "options": {
                            "temperature": config.temperature,
                            "num_predict": config.max_output_tokens,
                            "num_ctx": 8192,
                        },
                        "keep_alive": "5m",
                    },
                    config.timeout_seconds,
                )
                if response.get("model") != config.model:
                    raise AIError("MODEL_CHANGED")
                if response.get("done") is not True or response.get("done_reason") == "length":
                    raise AIError("INVALID_RESPONSE")
                message = response.get("message")
                if not isinstance(message, dict) or not isinstance(message.get("content"), str):
                    raise AIError("INVALID_RESPONSE")
                try:
                    raw = json.loads(message["content"])
                    if not isinstance(raw, dict):
                        raise AIError("INVALID_SCHEMA")
                    for key in ("claims", "entities", "actions"):
                        group = raw.get(key)
                        if not isinstance(group, list):
                            raise AIError("INVALID_SCHEMA")
                        for item in group:
                            if not isinstance(item, dict) or not isinstance(
                                item.get("evidence"), list
                            ):
                                raise AIError("INVALID_SCHEMA")
                            if any(not isinstance(e, str) for e in item["evidence"]):
                                raise AIError("INVALID_SCHEMA")
                            if any(e != anchor for e in item["evidence"]):
                                raise AIError("INVALID_LOCATOR")
                            item["evidence"] = [template for _ in item["evidence"]]
                    output = AnalysisOutputSchema.model_validate_json(json.dumps(raw))
                    if output.schema_version != config.schema_version:
                        raise AIError("INVALID_SCHEMA")
                except (ValidationError, ValueError) as exc:
                    raise AIError("INVALID_SCHEMA") from exc
            except AIError as exc:
                outcome = exc.code
                attempts.append(
                    CallAttempt(
                        started_at, datetime.now(UTC), perf_counter() - started, outcome, repair
                    )
                )
                if exc.code == "INVALID_SCHEMA" and not repair:
                    continue
                raise AIError(exc.code, tuple(attempts)) from exc
            attempts.append(
                CallAttempt(
                    started_at, datetime.now(UTC), perf_counter() - started, outcome, repair
                )
            )
            return AIResult(output, tuple(attempts))
        raise AssertionError("bounded repair exhausted")


def configured_ollama(
    config: AnalysisConfig, endpoint: str
) -> tuple[OllamaProcessor, AnalysisConfig]:
    from dataclasses import replace

    processor = OllamaProcessor(endpoint)
    revision, runtime = processor.metadata(config.model)
    return processor, replace(config, model_revision=revision, provider_revision=runtime)

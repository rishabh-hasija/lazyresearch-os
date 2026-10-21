"""Independent Ollama embedding adapter, sharing only the bounded HTTP transport."""

import math
from dataclasses import replace
from time import perf_counter

from lazyresearch.application.analysis_models import AIError
from lazyresearch.application.retrieval_models import (
    EmbeddingBatch,
    EmbeddingConfig,
    EmbeddingError,
)
from lazyresearch.infrastructure.ai.ollama import OllamaHTTP, OllamaProcessor, Wire


class OllamaEmbeddings:
    def __init__(self, endpoint: str, *, wire: Wire | None = None) -> None:
        self.wire = wire if wire is not None else OllamaHTTP(endpoint)

    def embed(
        self, texts: tuple[str, ...], config: EmbeddingConfig, *, query: bool = False
    ) -> EmbeddingBatch:
        if (
            not texts
            or len(texts) > config.batch_size
            or any(
                not t.strip() or len(t) > config.max_chars or len(t.encode()) > 4 * config.max_chars
                for t in texts
            )
        ):
            raise EmbeddingError("INPUT_BOUNDS")
        started = perf_counter()
        try:
            revision, runtime = OllamaProcessor("http://localhost", wire=self.wire).metadata(
                config.model
            )
            if config.revision is not None and revision is None:
                raise EmbeddingError("UNAVAILABLE")
            if config.revision is not None and revision != config.revision:
                raise EmbeddingError("MODEL_CHANGED")
            response = self.wire(
                "/api/embed",
                {
                    "model": config.model,
                    "input": [config.query_instruction + t if query else t for t in texts],
                    "truncate": False,
                    "options": {"num_ctx": 4096},
                    "keep_alive": "5m",
                },
                config.timeout,
            )
            if response.get("model") != config.model:
                raise EmbeddingError("MODEL_CHANGED")
            raw = response.get("embeddings")
            if not isinstance(raw, list) or len(raw) != len(texts):
                raise EmbeddingError("INVALID_RESPONSE")
            norms, vectors = [], []
            for value in raw:
                if (
                    not isinstance(value, list)
                    or len(value) != config.dimension
                    or any(
                        type(x) not in (float, int) or abs(x) > 1e100 or not math.isfinite(x)
                        for x in value
                    )
                ):
                    raise EmbeddingError("DIMENSION_OR_VALUES")
                norm = math.sqrt(sum(x * x for x in value))
                if norm <= 0:
                    raise EmbeddingError("ZERO_VECTOR")
                norms.append(norm)
                vectors.append(tuple(float(x / norm) for x in value))
            return EmbeddingBatch(
                tuple(vectors),
                replace(config, revision=revision),
                perf_counter() - started,
                runtime,
                tuple(norms),
            )
        except AIError as exc:
            raise EmbeddingError(exc.code) from exc

"""Synthetic labeled retrieval evaluation; explicit developer command, never pytest."""

import json
from dataclasses import asdict, replace
from pathlib import Path
from statistics import mean
from time import perf_counter
from uuid import uuid4

from sqlalchemy import text

from lazyresearch.application.intake_models import IntakeInput
from lazyresearch.application.retrieval import GenerateMissingEmbeddings
from lazyresearch.application.retrieval_models import RetrievalRequest
from lazyresearch.bootstrap import build_intake, build_retrieval
from lazyresearch.domain.content import SourceType
from lazyresearch.domain.identity import OwnerId
from lazyresearch.infrastructure.config import Settings
from lazyresearch.infrastructure.persistence.database import database_engine

CORPUS = {
    "solar": "Photovoltaic panels generate household electricity from sunlight.",
    "solar_near_duplicate": "Photovoltaic panels convert sunshine into electricity for homes.",
    "battery": "A rechargeable accumulator stores surplus rooftop energy for overnight use.",
    "heat": "A heat pump transfers outdoor warmth indoors and reduces gas heating.",
    "insulation": "Loft insulation and sealed attic gaps reduce winter heat loss.",
    "grant": "Municipal efficiency grant applications close on 2026-11-07. "
    "Complete the online funding form.",
    "cat": "A ginger kitten sleeps next to the fireplace after playing with a ball.",
    "train": "Berlin to Frankfurt intercity rail tickets require a seat reservation.",
    "tax": "Quarterly VAT filing uses the tax office portal and requires invoice totals.",
    "software": "API error RETRY_429 signals rate limiting. "
    "Use exponential backoff before retrying.",
    "flowers": "Tulips bloom in spring. Plant bulbs in a sunny garden with drained soil.",
    "cooking": "A sourdough starter needs flour, water and regular feeding before baking bread.",
    "long_manual": "Storage maintenance checks include cleaning vents and inspecting cables. " * 40,
}
QUERIES = (
    ("photovoltaic electricity", ("solar", "solar_near_duplicate")),
    ("power from sunshine", ("solar", "solar_near_duplicate")),
    ("overnight stored energy", ("battery",)),
    ("heat pump", ("heat",)),
    ("warmer attic in winter", ("insulation",)),
    ("grant applications", ("grant",)),
    ("2026-11-07", ("grant",)),
    ("pet napping by hearth", ("cat",)),
    ("rail tickets Frankfurt", ("train",)),
    ("RETRY_429", ("software",)),
    ("VAT filing", ("tax",)),
    ("online funding form", ("grant",)),
)


def main() -> None:
    settings = replace(Settings.from_env(), vector_search_enabled=True)
    engine = database_engine(settings.database_url)
    owner, outsider = OwnerId(uuid4()), OwnerId(uuid4())
    intake = build_intake(settings, engine=engine)
    usecase = build_retrieval(settings, engine=engine)
    ids = {}
    try:
        for key, value in CORPUS.items():
            result = intake.ingest(
                owner,
                key,
                (IntakeInput(source_type=SourceType.TEXT, payload=value.encode(), title=key),),
            )
            ids[key] = result.entries[0].content_id
        intake.ingest(
            outsider,
            "private",
            (
                IntakeInput(
                    source_type=SourceType.TEXT,
                    payload=b"Private photovoltaic electricity grant RETRY_429 VAT filing.",
                    title="private",
                ),
            ),
        )
        chunk_count = usecase.store.index(owner, usecase.chunks)
        usecase.store.index(outsider, usecase.chunks)
        started = perf_counter()
        indexed = GenerateMissingEmbeddings(
            usecase.vectors, usecase.provider, usecase.embeddings, usecase.chunks
        ).run(owner, limit=200)
        report = {
            "corpus_documents": len(ids),
            "owner_count": 2,
            "indexed_chunks": chunk_count,
            "queries": len(QUERIES),
            "k": 5,
            "chunk_config": asdict(usecase.chunks),
            "embedding_config": asdict(usecase.embeddings),
            "embedding_outcome": indexed,
            "index_seconds": perf_counter() - started,
            "modes": {},
        }
        with engine.connect() as c:
            report["pgvector_version"] = c.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname='vector'")
            )
        names = {str(value): key for key, value in ids.items()}
        for mode in ("lexical", "vector", "hybrid"):
            rows = []
            for query, expected in QUERIES:
                result = usecase.retrieve(
                    RetrievalRequest(
                        owner,
                        query,
                        lexical=mode != "vector",
                        vector=mode != "lexical",
                        limit=5,
                        per_source=2,
                    )
                )
                ranked_chunks = [
                    names.get(str(c.chunk.content_id), "CROSS_OWNER_ERROR")
                    for c in result.candidates
                ]
                assert all(c.chunk.owner_id == owner for c in result.candidates)
                assert "CROSS_OWNER_ERROR" not in ranked_chunks
                ranked = list(dict.fromkeys(ranked_chunks))
                relevant = set(expected)
                rows.append(
                    {
                        "query": query,
                        "expected": expected,
                        "documents": ranked,
                        "chunk_ids": [str(c.chunk.id) for c in result.candidates],
                        "recall_at_5": len(set(ranked) & relevant) / len(relevant),
                        "reciprocal_rank": next(
                            (1 / i for i, name in enumerate(ranked_chunks, 1) if name in relevant),
                            0,
                        ),
                        "source_diversity": len(ranked),
                        "seconds": result.latency_seconds,
                        "vector_status": result.vector_status,
                    }
                )
            report["modes"][mode] = {
                "recall_at_5": mean(r["recall_at_5"] for r in rows),
                "mrr": mean(r["reciprocal_rank"] for r in rows),
                "mean_source_diversity": mean(r["source_diversity"] for r in rows),
                "mean_seconds": mean(r["seconds"] for r in rows),
                "results": rows,
            }
        Path("docs/retrieval_benchmark_results.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        print(
            json.dumps(
                {
                    "embedding_outcome": indexed,
                    "chunks": chunk_count,
                    "pgvector": report["pgvector_version"],
                    "modes": {
                        k: {a: b for a, b in v.items() if a != "results"}
                        for k, v in report["modes"].items()
                    },
                },
                indent=2,
            ),
            flush=True,
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

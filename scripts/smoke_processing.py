"""Explicit synthetic PostgreSQL + configured AI smoke; creates a fresh synthetic owner."""

import json
from dataclasses import asdict
from uuid import uuid4

from lazyresearch.application.intake_models import IntakeInput
from lazyresearch.bootstrap import build_intake, build_processing
from lazyresearch.domain.content import SourceType
from lazyresearch.domain.identity import OwnerId
from lazyresearch.infrastructure.config import Settings
from lazyresearch.infrastructure.persistence.analysis import SQLAlchemyAnalysisStore
from lazyresearch.infrastructure.persistence.database import database_engine


def main() -> None:
    settings = Settings.from_env()
    engine = database_engine(settings.database_url)
    owner = OwnerId(uuid4())
    try:
        intake = build_intake(settings, engine=engine)
        saved = intake.ingest(
            owner,
            "synthetic-real-model-smoke",
            (
                IntakeInput(
                    source_type=SourceType.TEXT,
                    payload=b"Newsletter: Submit your workshop application by 2026-11-07. "
                    b"The workshop is organized by Cedar Labs.",
                ),
            ),
        )
        processing = build_processing(settings, engine=engine)
        result = processing.process_one(owner)
        analysis = (
            SQLAlchemyAnalysisStore(engine).get(owner, result.analysis_id)
            if result.analysis_id
            else None
        )
        print(
            json.dumps(
                {
                    "saved": saved.saved,
                    "processing": asdict(result),
                    "model": analysis.processing.model if analysis else None,
                    "model_revision": analysis.processing.model_revision if analysis else None,
                    "coverage": analysis.coverage if analysis else None,
                    "claims": len(analysis.claims) if analysis else 0,
                    "actions": len(analysis.proposals) if analysis else 0,
                    "deadlines": [str(p.deadline.normalized) for p in analysis.proposals]
                    if analysis
                    else [],
                },
                default=str,
                indent=2,
            )
        )
        if result.status != "SUCCEEDED":
            raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

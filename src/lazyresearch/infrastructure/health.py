"""Bounded, sanitized service probes. Details never include URLs, hosts or credentials."""

import json
import urllib.request
from dataclasses import dataclass

from sqlalchemy import text

from lazyresearch.infrastructure.config import Settings
from lazyresearch.infrastructure.persistence.database import database_engine
from lazyresearch.infrastructure.workflows.health import research_service_available

EXPECTED_MIGRATION = "0006"


@dataclass(frozen=True, slots=True)
class ServiceHealth:
    name: str
    ok: bool
    detail: str


def check_database(settings: Settings) -> ServiceHealth:
    try:
        engine = database_engine(settings.database_url)
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            vector = connection.execute(
                text("SELECT 1 FROM pg_extension WHERE extname='vector'")
            ).scalar()
        engine.dispose()
    except Exception:
        return ServiceHealth("database", False, "PostgreSQL unreachable or not migrated")
    if revision != EXPECTED_MIGRATION:
        return ServiceHealth("database", False, f"schema revision {revision}, expected 0006")
    return ServiceHealth("database", True, f"schema 0006; pgvector {'on' if vector else 'off'}")


def check_temporal(settings: Settings) -> ServiceHealth:
    if not settings.temporal_address:
        return ServiceHealth(
            "temporal",
            False,
            "Not checked: Temporal is not configured in this process; "
            "missions use PostgreSQL dispatch",
        )
    ok = research_service_available(settings)
    return ServiceHealth(
        "temporal",
        ok,
        "Temporal namespace reachable; worker activity not verified"
        if ok
        else "Temporal access not verified from this process; missions remain in PostgreSQL",
    )


def check_ai(settings: Settings) -> ServiceHealth:
    """Confirm the configured Ollama endpoint lists the configured generation model."""
    try:
        request = urllib.request.Request(settings.ai_endpoint.rstrip("/") + "/api/tags")
        with urllib.request.urlopen(request, timeout=3) as response:  # noqa: S310
            names = {m.get("name") for m in json.loads(response.read(1_000_000))["models"]}
    except Exception:
        return ServiceHealth("ai", False, "Model host unreachable")
    if settings.ai.model not in names:
        return ServiceHealth("ai", False, "Configured model is not installed on the model host")
    return ServiceHealth("ai", True, "Configured model available")


def check_all(settings: Settings) -> tuple[ServiceHealth, ...]:
    return (check_database(settings), check_temporal(settings), check_ai(settings))

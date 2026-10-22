import re
from pathlib import Path

from lazyresearch.application.demo_data import home_battery_inputs
from lazyresearch.infrastructure.config import Settings
from lazyresearch.infrastructure.health import check_ai, check_database

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = Settings.from_env({"DATABASE_URL": "postgresql://u:pw-secret@127.0.0.1:1/x"})


def test_render_blueprint_never_embeds_secrets_and_uses_health_path() -> None:
    text = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "healthCheckPath: /_stcore/health" in text
    for key in ("DATABASE_URL", "SERPAPI_API_KEY"):
        assert re.search(rf"key: {key}\n\s+sync: false", text)
    assert "postgres" not in text.lower().replace("postgresql is external", "")


def test_dockerfile_runs_unprivileged_without_migrating() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "USER app" in text and "alembic upgrade" not in text


def test_demo_fixtures_are_synthetic_and_distinct() -> None:
    inputs = home_battery_inputs()
    assert len(inputs) >= 5
    assert len({i.title for i in inputs}) == len(inputs)
    assert all(i.payload.startswith(b"SYNTHETIC DEMO FIXTURE.") for i in inputs)


def test_health_failures_are_sanitized() -> None:
    database = check_database(SETTINGS)
    assert not database.ok and "pw-secret" not in database.detail
    ai = check_ai(
        Settings.from_env(
            {**{"DATABASE_URL": "postgresql://x/y"}, "AI_ENDPOINT": "http://127.0.0.1:1"}
        )
    )
    assert not ai.ok and "127.0.0.1" not in ai.detail

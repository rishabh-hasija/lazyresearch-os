from dataclasses import replace

import pytest

from lazyresearch.application.intake_models import IntakeLimits
from lazyresearch.infrastructure.config import Settings
from lazyresearch.infrastructure.persistence.database import database_engine


def test_explicit_configuration_and_secret_repr() -> None:
    settings = Settings.from_env(
        {
            "DATABASE_URL": "postgresql://name:secret@localhost/test",
            "MAX_FETCH_BYTES": "100",
            "FETCH_TIMEOUT_SECONDS": "2.5",
        }
    )
    assert settings.limits.max_fetch_bytes == 100
    assert settings.limits.fetch_timeout_seconds == 2.5
    assert "secret" not in repr(settings)


def test_database_url_is_required() -> None:
    with pytest.raises(ValueError, match="DATABASE_URL"):
        Settings.from_env({})


def test_sqlite_cannot_substitute_for_postgresql() -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        database_engine("sqlite://")


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True])
def test_bad_limits_are_rejected(value) -> None:
    with pytest.raises(ValueError):
        replace(IntakeLimits(), fetch_timeout_seconds=value)

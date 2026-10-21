"""Shared deterministic value validation; no clocks, storage, or network access."""

from datetime import UTC, datetime
from uuid import UUID

from lazyresearch.domain.errors import DomainError


def require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DomainError(f"{field} must be nonblank text")


def require_id(value: UUID, field: str) -> None:
    if not isinstance(value, UUID):
        raise DomainError(f"{field} must be a UUID")


def require_count(value: int, field: str, *, minimum: int = 1) -> None:
    if type(value) is not int or value < minimum:
        raise DomainError(f"{field} must be an integer >= {minimum}")


def require_sha256(value: str, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise DomainError(f"{field} must be a lowercase SHA-256 hex digest")


def utc_instant(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DomainError(f"{field} requires a timezone-aware datetime")
    return value.astimezone(UTC)

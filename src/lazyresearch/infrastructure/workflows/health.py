"""Bounded read-only probe; no worker or in-memory mission fallback."""

import asyncio

from lazyresearch.infrastructure.config import Settings
from lazyresearch.infrastructure.workflows.connection import verify_temporal


def research_service_available(settings: Settings) -> bool:
    if not settings.temporal_address:
        return False
    try:
        asyncio.run(asyncio.wait_for(verify_temporal(settings), timeout=3))
        return True
    except Exception:
        return False

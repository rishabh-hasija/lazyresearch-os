"""Official SDK connection path shared by workers, dispatchers and probes."""

import asyncio
from datetime import timedelta

from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest
from temporalio.client import Client

from lazyresearch.infrastructure.config import Settings


class TemporalConnectionError(RuntimeError):
    """Sanitized connection/RPC failure, without SDK exception text."""


async def connect_temporal(settings: Settings) -> Client:
    settings.validate_temporal(required=True)
    try:
        return await asyncio.wait_for(
            Client.connect(
                settings.temporal_address,
                namespace=settings.temporal_namespace,
                api_key=settings.temporal_api_key or None,
                tls=settings.temporal_tls_enabled,
            ),
            timeout=10,
        )
    except Exception:
        raise TemporalConnectionError(
            "Temporal connection failed; check configuration and access"
        ) from None


async def verify_temporal(settings: Settings) -> None:
    """Read-only namespace access check; does not prove that a worker is polling."""
    client = await connect_temporal(settings)
    try:
        await client.workflow_service.describe_namespace(
            DescribeNamespaceRequest(namespace=settings.temporal_namespace),
            timeout=timedelta(seconds=5),
        )
    except Exception:
        raise TemporalConnectionError("Temporal namespace verification failed") from None

"""Bounded read-only service probe; no worker or in-memory mission fallback."""

import asyncio

from temporalio.client import Client


def research_service_available(address: str, namespace: str) -> bool:
    async def probe() -> bool:
        client = await Client.connect(address, namespace=namespace)
        return await client.service_client.check_health()

    try:
        return asyncio.run(asyncio.wait_for(probe(), timeout=3))
    except Exception:
        return False

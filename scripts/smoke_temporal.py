"""Read-only Temporal namespace smoke; never starts workflows or touches PostgreSQL."""

import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from lazyresearch.infrastructure.config import Settings
from lazyresearch.infrastructure.workflows.connection import verify_temporal


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    try:
        if args.env_file:
            if not args.env_file.is_file():
                print("Temporal smoke: FAIL (explicit env file is unavailable)")
                return 1
            load_dotenv(args.env_file, override=False, interpolate=False)
        # The shared settings object requires a DB URL. This smoke never uses it.
        settings = Settings.from_env({**os.environ, "DATABASE_URL": "postgresql://unused/smoke"})
        asyncio.run(asyncio.wait_for(verify_temporal(settings), timeout=20))
    except Exception:
        print("Temporal smoke: FAIL (check configuration, namespace permission and connectivity)")
        return 1
    print("Temporal connection and namespace access: PASS (read-only; no workflows started)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

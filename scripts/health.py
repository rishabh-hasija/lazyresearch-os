"""Deployment readiness probe. Exit 0 only if database is migrated; others are reported."""

import sys

from lazyresearch.infrastructure.config import Settings
from lazyresearch.infrastructure.health import check_all


def main() -> int:
    results = check_all(Settings.from_env())
    for item in results:
        print(f"{item.name}: {'ok' if item.ok else 'DEGRADED'} - {item.detail}")
    return 0 if results[0].ok else 1


if __name__ == "__main__":
    sys.exit(main())

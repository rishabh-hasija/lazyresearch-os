"""Hosted web entry point: binds 0.0.0.0 on $PORT. Never migrates or starts a worker."""

import os
import sys
from pathlib import Path


def main() -> None:
    from streamlit.web import cli

    from lazyresearch.infrastructure.config import Settings

    try:
        Settings.from_env()
    except ValueError as exc:
        sys.exit(f"Invalid configuration: {exc}")
    app = Path(__file__).resolve().parents[1] / "src/lazyresearch/ui/app.py"
    sys.argv = [
        "streamlit",
        "run",
        str(app),
        "--server.address=0.0.0.0",
        f"--server.port={os.environ.get('PORT', '10000')}",
        "--server.headless=true",
        "--server.enableXsrfProtection=true",
        "--browser.gatherUsageStats=false",
        "--client.toolbarMode=minimal",
    ]
    cli.main()


if __name__ == "__main__":
    main()

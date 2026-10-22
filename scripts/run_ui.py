"""Explicit local launcher; optional env-file loading is never implicit."""

import argparse
import os
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()
    if args.env_file:
        for line in args.env_file.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                name, value = line.split("=", 1)
                os.environ.setdefault(name.strip(), value.strip())
    from streamlit.web import cli

    app = Path(__file__).resolve().parents[1] / "src/lazyresearch/ui/app.py"
    sys.argv = [
        "streamlit",
        "run",
        str(app),
        "--server.address=127.0.0.1",
        f"--server.port={args.port}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    cli.main()


if __name__ == "__main__":
    main()

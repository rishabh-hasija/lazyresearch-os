"""Read-only AppTest timings: server rendering, excluding browser paint/cold start."""

import argparse
import logging
import time
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import event
from streamlit.testing.v1 import AppTest

from lazyresearch.bootstrap import build_workspace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()
    if args.env_file:
        if not args.env_file.is_file():
            parser.error("env file is missing")
        load_dotenv(args.env_file, override=False, interpolate=False)
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    work = build_workspace()
    app = AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "src/lazyresearch/ui/app.py"),
        default_timeout=180,
    )
    app.session_state["workspace"] = work
    # Repeat-visit ranking state, without creating observations during a read-only measure.
    app.session_state["ranking"] = ()
    counts = [0]

    def count(*_args):
        counts[0] += 1

    event.listen(work.reads.engine, "before_cursor_execute", count)
    app.run()
    for round_number in range(args.rounds):
        for section in ("Catch Up", "Research", "Actions", "Add Sources"):
            counts[0] = 0
            started = time.perf_counter()
            if app.sidebar.radio:
                app.sidebar.radio[0].set_value(section).run()
            else:
                label = "What Matters" if section == "Catch Up" else section
                next(b for b in app.sidebar.button if b.label == label).click().run()
            elapsed = time.perf_counter() - started
            if app.exception or app.error:
                raise RuntimeError("navigation did not render successfully")
            print(f"round={round_number + 1} page={section} seconds={elapsed:.3f} sql={counts[0]}")
    event.remove(work.reads.engine, "before_cursor_execute", count)


if __name__ == "__main__":
    main()

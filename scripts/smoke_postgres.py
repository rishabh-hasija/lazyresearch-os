"""Explicit synthetic UI/database smoke; no model or external action is invoked."""

import argparse
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text
from streamlit.testing.v1 import AppTest

from lazyresearch.bootstrap import build_retrieval, build_workspace
from lazyresearch.infrastructure.config import Settings
from lazyresearch.infrastructure.persistence.database import database_engine

TITLE = "Synthetic PostgreSQL setup smoke"
BODY = "SYNTHETIC DEMO FIXTURE. Neon persistence smoke: battery warranty is ten years."


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    load_dotenv(args.env_file, override=False, interpolate=False)
    settings = Settings.from_env()
    engine = database_engine(settings.database_url)
    with engine.connect() as connection:
        assert connection.connection.driver_connection.pgconn.ssl_in_use
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0006"
        )
    print("PostgreSQL pooled connection, client TLS and schema 0006: PASS")
    app_path = Path(__file__).resolve().parents[1] / "src/lazyresearch/ui/app.py"
    at = AppTest.from_file(str(app_path), default_timeout=60).run()
    assert not at.exception and not at.error
    work = at.session_state["workspace"]
    matches = [source for source in work.reads.sources(work.owner) if source.title == TITLE]
    if not args.verify_only and not matches:
        at.text_area[1].set_value(BODY)
        at.text_input[0].set_value(TITLE)
        next(button for button in at.button if button.label == "Save sources").click().run()
        assert not at.exception and not at.error
        matches = [source for source in work.reads.sources(work.owner) if source.title == TITLE]
        assert len(matches) == 1
        print("Streamlit Save sources -> PostgreSQL -> extracted source: PASS")
        work.index(work.owner)
    assert len(matches) == 1 and matches[0].text == BODY
    # New composition and fresh connections prove reads do not depend on session memory.
    engine.dispose()
    fresh = build_workspace(settings)
    stored = fresh.reads.source(fresh.owner, matches[0].id)
    assert stored is not None and stored.text == BODY
    retrieval = build_retrieval(settings)
    hits = retrieval.search(fresh.owner, "battery warranty")
    assert any(hit.chunk.content_id == stored.id for hit in hits.candidates)
    print("Fresh workspace source read and lexical retrieval: PASS")
    at.sidebar.radio[0].set_value("Catch Up").run()
    assert not at.exception and not at.error
    print("Streamlit Catch Up with live PostgreSQL: PASS")
    print("PostgreSQL end-to-end smoke: PASS")


if __name__ == "__main__":
    main()

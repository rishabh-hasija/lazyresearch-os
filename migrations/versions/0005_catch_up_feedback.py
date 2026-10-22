"""Immutable Catch Up observations and explicit feedback.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ranking_observation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("content_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_id", sa.Uuid()),
        sa.Column("analysis_id", sa.Uuid()),
        sa.Column("cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.UniqueConstraint("owner_id", "content_id", "id"),
        sa.ForeignKeyConstraint(
            ["owner_id", "content_id"], ["content_item.owner_id", "content_item.id"]
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "content_id", "extraction_id"],
            [
                "content_extraction.owner_id",
                "content_extraction.content_id",
                "content_extraction.id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "analysis_id"], ["content_analysis.owner_id", "content_analysis.id"]
        ),
        sa.CheckConstraint("cutoff <= recorded_at", name="ranking_cutoff"),
    )
    op.create_index(
        "ix_ranking_owner_content", "ranking_observation", ["owner_id", "content_id", "cutoff"]
    )
    op.create_table(
        "user_interaction",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("content_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("explicit", sa.Boolean(), nullable=False),
        sa.Column("observation_id", sa.Uuid()),
        sa.Column("label", sa.Text()),
        sa.Column("supersedes", sa.Uuid()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.UniqueConstraint("owner_id", "content_id", "id"),
        sa.UniqueConstraint("supersedes"),
        sa.ForeignKeyConstraint(
            ["owner_id", "content_id"], ["content_item.owner_id", "content_item.id"]
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "content_id", "observation_id"],
            [
                "ranking_observation.owner_id",
                "ranking_observation.content_id",
                "ranking_observation.id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "content_id", "supersedes"],
            ["user_interaction.owner_id", "user_interaction.content_id", "user_interaction.id"],
        ),
        sa.CheckConstraint(
            "kind IN ('ITEM_OPENED','ITEM_IGNORED','ITEM_ARCHIVED','ITEM_SAVED',"
            "'ITEM_ACTED_ON','ITEM_RESURFACED','MISSION_USED_ITEM','FEEDBACK_LABELED')",
            name="interaction_kind",
        ),
        sa.CheckConstraint(
            "label IS NULL OR label IN ('READ','KEEP','ACT','IGNORE')", name="interaction_label"
        ),
        sa.CheckConstraint(
            "(kind='FEEDBACK_LABELED') = (label IS NOT NULL)", name="interaction_target"
        ),
        sa.CheckConstraint(
            "label IS NULL OR (explicit AND observation_id IS NOT NULL)",
            name="interaction_explicit",
        ),
        sa.CheckConstraint(
            "supersedes IS NULL OR (label IS NOT NULL AND supersedes<>id)",
            name="interaction_supersedes",
        ),
        sa.CheckConstraint("occurred_at <= recorded_at", name="interaction_time"),
    )
    op.create_index(
        "ix_interaction_owner_content",
        "user_interaction",
        ["owner_id", "content_id", "recorded_at"],
    )
    op.execute("""
    CREATE FUNCTION ranking_observation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE a content_analysis;
    BEGIN
      IF NEW.analysis_id IS NOT NULL THEN
        SELECT * INTO a FROM content_analysis WHERE owner_id=NEW.owner_id AND id=NEW.analysis_id;
        IF a.content_id IS DISTINCT FROM NEW.content_id
           OR a.extraction_id IS DISTINCT FROM NEW.extraction_id OR a.created_at>=NEW.cutoff
        THEN RAISE EXCEPTION 'invalid ranking analysis'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER ranking_observation_guard BEFORE INSERT ON ranking_observation
    FOR EACH ROW EXECUTE FUNCTION ranking_observation_guard();
    CREATE FUNCTION interaction_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE previous user_interaction; observation ranking_observation;
    BEGIN
      PERFORM id FROM content_item WHERE owner_id=NEW.owner_id AND id=NEW.content_id FOR UPDATE;
      IF NEW.label IS NOT NULL THEN
        SELECT * INTO observation FROM ranking_observation WHERE id=NEW.observation_id
          AND owner_id=NEW.owner_id AND content_id=NEW.content_id;
        IF observation.id IS NULL OR observation.cutoff>=NEW.occurred_at
           OR observation.recorded_at>=NEW.recorded_at
        THEN RAISE EXCEPTION 'feedback must follow observation'; END IF;
        SELECT * INTO previous FROM user_interaction WHERE owner_id=NEW.owner_id
          AND content_id=NEW.content_id AND label IS NOT NULL
          ORDER BY recorded_at DESC, id DESC LIMIT 1;
        IF previous.id IS DISTINCT FROM NEW.supersedes
           OR (previous.id IS NOT NULL AND previous.occurred_at>NEW.occurred_at)
        THEN RAISE EXCEPTION 'stale label correction'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER interaction_guard BEFORE INSERT ON user_interaction
    FOR EACH ROW EXECUTE FUNCTION interaction_guard();
    """)
    for table in ("ranking_observation", "user_interaction"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION research_immutable()"
        )


def downgrade() -> None:
    op.drop_table("user_interaction")
    op.drop_table("ranking_observation")
    op.execute("DROP FUNCTION interaction_guard(), ranking_observation_guard()")

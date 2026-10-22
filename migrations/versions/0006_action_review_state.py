"""User task state separate from immutable proposals.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid()),
        sa.Column("result_id", sa.Uuid()),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("deadline_raw", sa.Text()),
        sa.Column("deadline_normalized", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.UniqueConstraint("owner_id", "id"),
        sa.UniqueConstraint("owner_id", "proposal_id"),
        sa.ForeignKeyConstraint(
            ["owner_id", "analysis_id"], ["content_analysis.owner_id", "content_analysis.id"]
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "result_id"], ["research_result.owner_id", "research_result.id"]
        ),
        sa.CheckConstraint("(analysis_id IS NULL) <> (result_id IS NULL)", name="task_origin"),
        sa.CheckConstraint(
            "status IN ('PROPOSED','ACCEPTED','COMPLETED','DISMISSED')", name="task_status"
        ),
        sa.CheckConstraint("revision>=0", name="task_revision"),
        sa.CheckConstraint(
            "length(trim(title))>0 AND length(trim(description))>0", name="task_text"
        ),
    )
    op.execute("""
    CREATE FUNCTION action_item_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='INSERT' THEN
        IF NEW.revision<>0 OR NEW.status<>'PROPOSED' THEN
          RAISE EXCEPTION 'initial task state'; END IF;
        IF NEW.analysis_id IS NOT NULL THEN
          IF NOT EXISTS(SELECT 1 FROM action_proposal WHERE id=NEW.proposal_id
             AND owner_id=NEW.owner_id AND analysis_id=NEW.analysis_id)
          THEN RAISE EXCEPTION 'invalid source proposal'; END IF;
        ELSE
          IF NOT EXISTS(SELECT 1 FROM research_proposal WHERE id=NEW.proposal_id
             AND owner_id=NEW.owner_id AND result_id=NEW.result_id)
          THEN RAISE EXCEPTION 'invalid research proposal'; END IF;
        END IF;
      ELSE
        IF (NEW.id,NEW.owner_id,NEW.proposal_id,NEW.analysis_id,NEW.result_id)
           IS DISTINCT FROM (OLD.id,OLD.owner_id,OLD.proposal_id,OLD.analysis_id,OLD.result_id)
           OR NEW.revision<>OLD.revision+1 THEN RAISE EXCEPTION 'task identity or revision'; END IF;
        IF NEW.status<>OLD.status AND NOT (
          (OLD.status='PROPOSED' AND NEW.status IN ('ACCEPTED','DISMISSED')) OR
          (OLD.status='ACCEPTED' AND NEW.status IN ('COMPLETED','DISMISSED')) OR
          (OLD.status IN ('COMPLETED','DISMISSED') AND NEW.status='ACCEPTED'))
        THEN RAISE EXCEPTION 'task transition'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER action_item_guard BEFORE INSERT OR UPDATE ON action_item
    FOR EACH ROW EXECUTE FUNCTION action_item_guard();
    """)


def downgrade() -> None:
    op.drop_table("action_item")
    op.execute("DROP FUNCTION action_item_guard()")

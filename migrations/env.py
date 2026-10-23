"""DATABASE_URL must be explicitly supplied; never migrate during application startup."""

import os

from alembic import context

from lazyresearch.infrastructure.persistence import (  # noqa: F401
    mission_models,
    ranking_models,
    retrieval_models,
    workspace_models,
)
from lazyresearch.infrastructure.persistence.database import database_engine
from lazyresearch.infrastructure.persistence.models import Base


def include_object(obj, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    # Optional native storage is explicitly managed by 0003, outside portable ORM metadata.
    return name != "embedding_vector"


def include_name(name, type_, parent_names):  # type: ignore[no-untyped-def]
    return type_ != "table" or name != "embedding_vector"


config = context.config
database_url = os.environ.get("DATABASE_URL_UNPOOLED") or os.environ.get("DATABASE_URL", "")
connection = config.attributes.get("connection")
if connection is not None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        include_object=include_object,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()
elif context.is_offline_mode():
    context.configure(
        url=database_url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = database_engine(database_url)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            include_object=include_object,
            include_name=include_name,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()

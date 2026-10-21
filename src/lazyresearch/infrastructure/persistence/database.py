from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url


def database_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("LazyResearch persistence requires PostgreSQL")
    url = url.set(drivername="postgresql+psycopg")
    return create_engine(url, pool_pre_ping=True, hide_parameters=True)

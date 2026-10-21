"""Provider-neutral repository errors; adapters must translate storage exceptions."""


class RepositoryError(Exception):
    """Storage failed; callers must not assume any write succeeded."""


class RepositoryConflict(RepositoryError):
    """Immutable identity conflict, ownership mismatch, or stale stored revision."""

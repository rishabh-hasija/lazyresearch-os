"""Task state persistence contract with ownership and optimistic-revision semantics."""

from typing import Protocol

from lazyresearch.domain.actions import ActionItem
from lazyresearch.domain.identity import ActionId, OwnerId


class ActionRepository(Protocol):
    def get(self, owner_id: OwnerId, action_id: ActionId) -> ActionItem | None:
        """Missing/other-owner return None; storage failures raise RepositoryError."""
        ...

    def save(
        self,
        owner_id: OwnerId,
        item: ActionItem,
        *,
        expected_revision: int | None,
    ) -> None:
        """None inserts revision 0; an exact repeated insert by ID is a no-op.

        Updates require stored revision == expected_revision and item revision
        == expected_revision + 1. Preserve proposal/evidence identity and owner.
        Owner mismatch, stale revision or conflicting IDs raise RepositoryConflict;
        other storage failures raise RepositoryError. Future adapters must enforce
        the owner + origin + candidate ordinal proposal uniqueness atomically.
        """
        ...

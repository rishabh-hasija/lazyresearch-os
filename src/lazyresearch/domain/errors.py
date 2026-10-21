"""Small, explicit error vocabulary shared by domain and port contracts."""


class DomainError(ValueError):
    """An operation would violate a domain invariant."""


class InvalidStateTransition(DomainError):
    """The current state does not permit the requested transition."""


class MissingProvenance(DomainError):
    """Generated information lacks original source evidence."""


class InvalidResearchPublication(DomainError):
    """Publication is inconsistent with the mission or its published history."""


class RevisionConflict(DomainError):
    """A user edit was based on an outdated task revision."""

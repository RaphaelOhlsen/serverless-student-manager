class InvalidAuditQueryRequestError(ValueError):
    """The public audit query parameters are invalid."""


class InvalidAuditCursorError(ValueError):
    """The audit query cursor is malformed or incompatible with the query."""


class AuditEventDataInvariantError(RuntimeError):
    """A stored audit event cannot be represented safely."""


class AuditForbiddenError(PermissionError):
    """The authoritative user state does not permit audit access."""

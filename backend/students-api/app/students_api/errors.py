class StudentNotFoundError(Exception):
    """Raised when a student cannot be found."""


class ForbiddenError(Exception):
    """Raised when the authenticated identity is not allowed to list students."""


class InvalidListRequestError(Exception):
    """Raised when list query parameters or a cursor are invalid."""

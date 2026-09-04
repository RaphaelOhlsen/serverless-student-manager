class StudentNotFoundError(Exception):
    """Raised when a student cannot be found."""


class ForbiddenError(Exception):
    """Raised when the authenticated identity is not allowed to list students."""


class InvalidListRequestError(Exception):
    """Raised when list query parameters or a cursor are invalid."""


class InvalidCreateStudentRequestError(Exception):
    """Raised when a create-student request violates the public contract."""


class RegistrationNumberAlreadyExistsError(Exception):
    """Raised when the normalized registration number is reserved."""


class StudentEmailAlreadyExistsError(Exception):
    """Raised when the normalized student email is reserved."""


class StudentUniquenessConflictError(Exception):
    """Raised when registration number and email are both reserved."""


class IdempotencyKeyReusedError(Exception):
    """Raised when an idempotency key is reused with a different payload."""


class OperationInProgressError(Exception):
    """Raised when the same idempotent operation is still running."""

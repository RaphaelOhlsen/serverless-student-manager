class InvalidActivationRequestError(ValueError):
    pass


class ActivationUnauthorizedError(RuntimeError):
    pass


class ActivationForbiddenError(RuntimeError):
    pass


class ActivationConflictError(RuntimeError):
    pass


class SelfProfileUnauthorizedError(RuntimeError):
    pass


class SelfProfileForbiddenError(RuntimeError):
    pass


class InvalidAdminUserListRequestError(ValueError):
    pass


class AdminUserUnauthorizedError(RuntimeError):
    pass


class AdminUserForbiddenError(RuntimeError):
    pass


class AdminUserNotFoundError(RuntimeError):
    pass


class AdminUserDataInvariantError(RuntimeError):
    pass

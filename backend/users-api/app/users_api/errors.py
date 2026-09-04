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

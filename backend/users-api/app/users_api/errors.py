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


class InvalidAdminUserWriteRequestError(ValueError):
    pass


class IdempotencyKeyReusedError(RuntimeError):
    pass


class OperationInProgressError(RuntimeError):
    pass


class InvitationSagaInvariantError(RuntimeError):
    pass


class InvitationSagaConcurrentTransitionError(RuntimeError):
    pass


class CognitoUserNotFoundError(RuntimeError):
    pass


class CognitoUsernameExistsError(RuntimeError):
    pass


class CognitoAliasExistsError(RuntimeError):
    pass


class CognitoResultAmbiguousError(RuntimeError):
    pass


class CognitoCreateDeterministicError(RuntimeError):
    pass


class CognitoServiceError(RuntimeError):
    pass


class CognitoIdentityInvariantError(RuntimeError):
    pass


class UserEmailAlreadyExistsError(RuntimeError):
    pass


class CognitoInvitationDeliveryError(RuntimeError):
    pass


class InvitationDeliveryFailedError(RuntimeError):
    pass


class InvitationDeliveryUncertainError(RuntimeError):
    pass


class UserCreateReconciliationError(RuntimeError):
    pass


class UserVersionConflictError(RuntimeError):
    pass


class UserStateConflictError(RuntimeError):
    pass


class UserInvitationReconciliationError(RuntimeError):
    pass


class LastActiveAdminConflictError(RuntimeError):
    pass


class UserRoleChangeReconciliationError(RuntimeError):
    pass


class UserDeactivationReconciliationError(RuntimeError):
    pass


class UserReactivationReconciliationError(RuntimeError):
    pass

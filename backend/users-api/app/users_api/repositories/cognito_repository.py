from dataclasses import dataclass
from typing import Any, Never, Protocol, cast
from uuid import UUID

from botocore.exceptions import (  # type: ignore[import-untyped]
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

from users_api.errors import (
    CognitoAliasExistsError,
    CognitoCreateDeterministicError,
    CognitoIdentityInvariantError,
    CognitoInvitationDeliveryError,
    CognitoResultAmbiguousError,
    CognitoServiceError,
    CognitoUsernameExistsError,
    CognitoUserNotFoundError,
)
from users_api.validation import normalize_admin_user_email

_AMBIGUOUS_TRANSPORT_ERRORS = (
    ConnectTimeoutError,
    ReadTimeoutError,
    ConnectionClosedError,
    EndpointConnectionError,
)
_DETERMINISTIC_CREATE_CODES = {
    "InvalidParameterException",
    "InvalidPasswordException",
    "ResourceNotFoundException",
    "TooManyRequestsException",
}


class CognitoClient(Protocol):
    def admin_create_user(self, **kwargs: object) -> dict[str, Any]: ...

    def admin_get_user(self, **kwargs: object) -> dict[str, Any]: ...

    def admin_get_user_auth_factors(self, **kwargs: object) -> dict[str, Any]: ...

    def admin_delete_user(self, **kwargs: object) -> dict[str, Any]: ...

    def admin_disable_user(self, **kwargs: object) -> dict[str, Any]: ...


class CognitoDeactivationClient(Protocol):
    def admin_user_global_sign_out(self, **kwargs: object) -> dict[str, Any]: ...


class CognitoReactivationClient(Protocol):
    def admin_enable_user(self, **kwargs: object) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ReconciledCognitoIdentity:
    user_id: str
    cognito_sub: str


@dataclass(frozen=True)
class ReconciledCognitoDeactivationState:
    user_id: str
    cognito_sub: str
    enabled: bool


@dataclass(frozen=True)
class ReconciledCognitoReactivationState:
    user_id: str
    cognito_sub: str
    enabled: bool


class CognitoRepository:
    def __init__(self, client: CognitoClient, user_pool_id: str) -> None:
        self._client = client
        self._user_pool_id = user_pool_id

    def admin_create_user(self, *, user_id: str, email: str) -> None:
        normalized_email = normalize_admin_user_email(email)
        try:
            self._client.admin_create_user(
                UserPoolId=self._user_pool_id,
                Username=user_id,
                UserAttributes=[
                    {"Name": "email", "Value": normalized_email},
                    {"Name": "email_verified", "Value": "true"},
                ],
                MessageAction="SUPPRESS",
                ForceAliasCreation=False,
            )
        except Exception as error:
            self._raise_create_error(error)

    def admin_get_user(
        self,
        *,
        user_id: str,
        expected_email: str,
    ) -> ReconciledCognitoIdentity:
        try:
            response = self._client.admin_get_user(
                UserPoolId=self._user_pool_id,
                Username=user_id,
            )
        except Exception as error:
            self._raise_read_error(error)
        return self._parse_identity(response, user_id=user_id, expected_email=expected_email)

    def get_user(self, user_id: str) -> dict[str, Any]:
        return self._client.admin_get_user(
            UserPoolId=self._user_pool_id,
            Username=user_id,
        )

    def get_user_auth_factors(self, user_id: str) -> dict[str, Any]:
        return self._client.admin_get_user_auth_factors(
            UserPoolId=self._user_pool_id,
            Username=user_id,
        )

    def admin_delete_user(self, *, user_id: str) -> None:
        self._compensation_call("delete", user_id=user_id)

    def admin_disable_user(self, *, user_id: str) -> None:
        self._compensation_call("disable", user_id=user_id)

    def admin_user_global_sign_out(self, *, user_id: str) -> None:
        client = cast(CognitoDeactivationClient, self._client)
        try:
            client.admin_user_global_sign_out(
                UserPoolId=self._user_pool_id,
                Username=user_id,
            )
        except Exception as error:
            self._raise_read_error(error)

    def admin_get_deactivation_state(
        self,
        *,
        user_id: str,
        expected_cognito_sub: str,
    ) -> ReconciledCognitoDeactivationState:
        try:
            response = self._client.admin_get_user(
                UserPoolId=self._user_pool_id,
                Username=user_id,
            )
        except Exception as error:
            self._raise_read_error(error)
        return self._parse_deactivation_state(
            response,
            user_id=user_id,
            expected_cognito_sub=expected_cognito_sub,
        )

    def admin_get_reactivation_state(
        self,
        *,
        user_id: str,
        expected_cognito_sub: str,
        expected_email: str,
        expected_enabled: bool | None,
    ) -> ReconciledCognitoReactivationState:
        try:
            response = self._client.admin_get_user(
                UserPoolId=self._user_pool_id,
                Username=user_id,
            )
        except Exception as error:
            self._raise_reactivation_read_error(error)
        return self._parse_reactivation_state(
            response,
            user_id=user_id,
            expected_cognito_sub=expected_cognito_sub,
            expected_email=expected_email,
            expected_enabled=expected_enabled,
        )

    def admin_enable_user(self, *, user_id: str) -> None:
        client = cast(CognitoReactivationClient, self._client)
        try:
            response = client.admin_enable_user(
                UserPoolId=self._user_pool_id,
                Username=user_id,
            )
        except Exception as error:
            self._raise_enable_error(error)
        if not isinstance(response, dict):
            raise CognitoResultAmbiguousError from None

    def admin_resend_invitation(self, *, user_id: str) -> None:
        try:
            self._client.admin_create_user(
                UserPoolId=self._user_pool_id,
                Username=user_id,
                MessageAction="RESEND",
            )
        except Exception as error:
            code, http_status = self._error_details(error)
            if self._is_ambiguous(error, code, http_status):
                raise CognitoResultAmbiguousError from None
            if isinstance(error, ClientError):
                raise CognitoInvitationDeliveryError from None
            raise

    def _compensation_call(self, operation: str, *, user_id: str) -> None:
        try:
            if operation == "delete":
                self._client.admin_delete_user(
                    UserPoolId=self._user_pool_id,
                    Username=user_id,
                )
            else:
                self._client.admin_disable_user(
                    UserPoolId=self._user_pool_id,
                    Username=user_id,
                )
        except Exception as error:
            self._raise_read_error(error)

    @staticmethod
    def _parse_identity(
        response: object,
        *,
        user_id: str,
        expected_email: str,
    ) -> ReconciledCognitoIdentity:
        if not isinstance(response, dict):
            raise CognitoIdentityInvariantError("Cognito response is malformed")
        if response.get("Username") != user_id:
            raise CognitoIdentityInvariantError("Cognito username is incompatible")
        attributes = response.get("UserAttributes")
        if not isinstance(attributes, list):
            raise CognitoIdentityInvariantError("Cognito attributes are malformed")

        relevant: dict[str, str] = {}
        for attribute in attributes:
            if not isinstance(attribute, dict):
                raise CognitoIdentityInvariantError("Cognito attribute is malformed")
            name = attribute.get("Name")
            value = attribute.get("Value")
            if not isinstance(name, str) or not isinstance(value, str):
                raise CognitoIdentityInvariantError("Cognito attribute is malformed")
            if name not in {"sub", "email", "email_verified"}:
                continue
            if name in relevant:
                raise CognitoIdentityInvariantError("Cognito identity attribute is duplicated")
            relevant[name] = value

        cognito_sub = relevant.get("sub")
        if cognito_sub is None or not CognitoRepository._is_canonical_uuid(cognito_sub):
            raise CognitoIdentityInvariantError("Cognito sub is missing or invalid")
        email = relevant.get("email")
        if email is None:
            raise CognitoIdentityInvariantError("Cognito email is missing")
        try:
            actual_email = normalize_admin_user_email(email)
            normalized_expected = normalize_admin_user_email(expected_email)
        except ValueError:
            raise CognitoIdentityInvariantError("Cognito email is invalid") from None
        if actual_email != normalized_expected:
            raise CognitoIdentityInvariantError("Cognito email is incompatible")
        if relevant.get("email_verified") != "true":
            raise CognitoIdentityInvariantError("Cognito email is not verified")
        return ReconciledCognitoIdentity(user_id=user_id, cognito_sub=cognito_sub)

    @staticmethod
    def _parse_deactivation_state(
        response: object,
        *,
        user_id: str,
        expected_cognito_sub: str,
    ) -> ReconciledCognitoDeactivationState:
        if not isinstance(response, dict):
            raise CognitoIdentityInvariantError("Cognito response is malformed")
        if response.get("Username") != user_id:
            raise CognitoIdentityInvariantError("Cognito username is incompatible")
        enabled = response.get("Enabled")
        if type(enabled) is not bool:
            raise CognitoIdentityInvariantError("Cognito enabled state is malformed")
        attributes = response.get("UserAttributes")
        if not isinstance(attributes, list):
            raise CognitoIdentityInvariantError("Cognito attributes are malformed")
        subs: list[str] = []
        for attribute in attributes:
            if not isinstance(attribute, dict):
                raise CognitoIdentityInvariantError("Cognito attribute is malformed")
            name = attribute.get("Name")
            value = attribute.get("Value")
            if not isinstance(name, str) or not isinstance(value, str):
                raise CognitoIdentityInvariantError("Cognito attribute is malformed")
            if name == "sub":
                subs.append(value)
        if len(subs) != 1 or not CognitoRepository._is_canonical_uuid(subs[0]):
            raise CognitoIdentityInvariantError("Cognito sub is missing, duplicated, or invalid")
        if subs[0] != expected_cognito_sub:
            raise CognitoIdentityInvariantError("Cognito sub is incompatible")
        return ReconciledCognitoDeactivationState(
            user_id=user_id,
            cognito_sub=subs[0],
            enabled=enabled,
        )

    @staticmethod
    def _parse_reactivation_state(
        response: object,
        *,
        user_id: str,
        expected_cognito_sub: str,
        expected_email: str,
        expected_enabled: bool | None,
    ) -> ReconciledCognitoReactivationState:
        if expected_enabled is not None and type(expected_enabled) is not bool:
            raise CognitoIdentityInvariantError("Expected Cognito enabled state is invalid")
        if not CognitoRepository._is_canonical_uuid(expected_cognito_sub):
            raise CognitoIdentityInvariantError("Expected Cognito sub is invalid")
        if not isinstance(response, dict):
            raise CognitoIdentityInvariantError("Cognito response is malformed")
        if response.get("Username") != user_id:
            raise CognitoIdentityInvariantError("Cognito username is incompatible")
        if response.get("UserStatus") != "CONFIRMED":
            raise CognitoIdentityInvariantError("Cognito user status is incompatible")
        enabled = response.get("Enabled")
        if type(enabled) is not bool:
            raise CognitoIdentityInvariantError("Cognito enabled state is malformed")
        if expected_enabled is not None and enabled is not expected_enabled:
            raise CognitoIdentityInvariantError("Cognito enabled state is incompatible")
        attributes = response.get("UserAttributes")
        if not isinstance(attributes, list):
            raise CognitoIdentityInvariantError("Cognito attributes are malformed")

        relevant: dict[str, str] = {}
        for attribute in attributes:
            if not isinstance(attribute, dict):
                raise CognitoIdentityInvariantError("Cognito attribute is malformed")
            name = attribute.get("Name")
            value = attribute.get("Value")
            if not isinstance(name, str) or not isinstance(value, str):
                raise CognitoIdentityInvariantError("Cognito attribute is malformed")
            if name not in {"sub", "email", "email_verified"}:
                continue
            if name in relevant:
                raise CognitoIdentityInvariantError("Cognito identity attribute is duplicated")
            relevant[name] = value

        cognito_sub = relevant.get("sub")
        if cognito_sub is None or not CognitoRepository._is_canonical_uuid(cognito_sub):
            raise CognitoIdentityInvariantError("Cognito sub is missing or invalid")
        if cognito_sub != expected_cognito_sub:
            raise CognitoIdentityInvariantError("Cognito sub is incompatible")
        email = relevant.get("email")
        if email is None:
            raise CognitoIdentityInvariantError("Cognito email is missing")
        try:
            actual_email = normalize_admin_user_email(email)
            normalized_expected = normalize_admin_user_email(expected_email)
        except ValueError:
            raise CognitoIdentityInvariantError("Cognito email is invalid") from None
        if actual_email != normalized_expected:
            raise CognitoIdentityInvariantError("Cognito email is incompatible")
        if relevant.get("email_verified") != "true":
            raise CognitoIdentityInvariantError("Cognito email is not verified")
        return ReconciledCognitoReactivationState(
            user_id=user_id,
            cognito_sub=cognito_sub,
            enabled=enabled,
        )

    @staticmethod
    def _raise_create_error(error: Exception) -> Never:
        code, http_status = CognitoRepository._error_details(error)
        if code == "UsernameExistsException":
            raise CognitoUsernameExistsError from None
        if code == "AliasExistsException":
            raise CognitoAliasExistsError from None
        if CognitoRepository._is_ambiguous(error, code, http_status):
            raise CognitoResultAmbiguousError from None
        if code in _DETERMINISTIC_CREATE_CODES:
            raise CognitoCreateDeterministicError from None
        if isinstance(error, ClientError):
            raise CognitoServiceError from None
        raise error

    @staticmethod
    def _raise_read_error(error: Exception) -> Never:
        code, http_status = CognitoRepository._error_details(error)
        if code == "UserNotFoundException":
            raise CognitoUserNotFoundError from None
        if CognitoRepository._is_ambiguous(error, code, http_status):
            raise CognitoResultAmbiguousError from None
        if isinstance(error, ClientError):
            raise CognitoServiceError from None
        raise error

    @staticmethod
    def _raise_reactivation_read_error(error: Exception) -> Never:
        code, http_status = CognitoRepository._error_details(error)
        if code == "UserNotFoundException":
            raise CognitoUserNotFoundError from None
        if CognitoRepository._is_ambiguous(error, code, http_status):
            raise CognitoResultAmbiguousError from None
        raise CognitoServiceError from None

    @staticmethod
    def _raise_enable_error(error: Exception) -> Never:
        code, http_status = CognitoRepository._error_details(error)
        if code == "UserNotFoundException":
            raise CognitoUserNotFoundError from None
        if CognitoRepository._is_ambiguous(error, code, http_status) or not isinstance(
            error, ClientError
        ):
            raise CognitoResultAmbiguousError from None
        raise CognitoServiceError from None

    @staticmethod
    def _is_ambiguous(error: Exception, code: str | None, http_status: int | None) -> bool:
        return (
            isinstance(error, _AMBIGUOUS_TRANSPORT_ERRORS)
            or code == "InternalErrorException"
            or (http_status is not None and 500 <= http_status <= 599)
        )

    @staticmethod
    def _error_details(error: Exception) -> tuple[str | None, int | None]:
        response = getattr(error, "response", None)
        if not isinstance(response, dict):
            return None, None
        details = response.get("Error")
        code = details.get("Code") if isinstance(details, dict) else None
        metadata = response.get("ResponseMetadata")
        http_status = metadata.get("HTTPStatusCode") if isinstance(metadata, dict) else None
        return (
            code if isinstance(code, str) else None,
            http_status if type(http_status) is int else None,
        )

    @staticmethod
    def _is_canonical_uuid(value: str) -> bool:
        try:
            return str(UUID(value)) == value
        except ValueError:
            return False

from dataclasses import dataclass
from typing import Any, Protocol

from tools.bootstrap_admin.normalization import normalize_email


class CognitoClient(Protocol):
    def admin_create_user(self, **kwargs: object) -> dict[str, Any]: ...

    def admin_get_user(self, **kwargs: object) -> dict[str, Any]: ...

    def admin_update_user_attributes(self, **kwargs: object) -> dict[str, Any]: ...

    def admin_delete_user(self, **kwargs: object) -> dict[str, Any]: ...

    def admin_disable_user(self, **kwargs: object) -> dict[str, Any]: ...


class CognitoIdentityValidationError(RuntimeError):
    pass


class CognitoCreateResultError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReconciledCognitoIdentity:
    cognito_sub: str
    verified: bool


class CognitoRepository:
    def __init__(self, client: CognitoClient) -> None:
        self._client = client

    def create_suppressed_user(
        self,
        *,
        user_pool_id: str,
        user_id: str,
        email: str,
    ) -> str:
        response = self._client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=user_id,
            UserAttributes=[
                {
                    "Name": "email",
                    "Value": email,
                },
                {
                    "Name": "email_verified",
                    "Value": "true",
                },
            ],
            MessageAction="SUPPRESS",
            ForceAliasCreation=False,
        )

        user = response.get("User")

        if not isinstance(user, dict):
            raise CognitoCreateResultError("Cognito AdminCreateUser response is missing User")

        attributes = user.get("Attributes")

        if not isinstance(attributes, list):
            raise CognitoCreateResultError("Cognito AdminCreateUser response is missing Attributes")

        for attribute in attributes:
            if not isinstance(attribute, dict):
                continue

            if attribute.get("Name") != "sub":
                continue

            value = attribute.get("Value")

            if isinstance(value, str):
                return value

        raise CognitoCreateResultError("Cognito AdminCreateUser response is missing sub")

    def get_existing_user_sub(
        self,
        *,
        user_pool_id: str,
        user_id: str,
        expected_email: str,
    ) -> str:
        response = self._client.admin_get_user(
            UserPoolId=user_pool_id,
            Username=user_id,
        )

        attributes = response.get("UserAttributes")

        if not isinstance(attributes, list):
            raise CognitoIdentityValidationError(
                "Cognito AdminGetUser response is missing UserAttributes"
            )

        cognito_sub: str | None = None
        cognito_email: str | None = None

        for attribute in attributes:
            if not isinstance(attribute, dict):
                continue

            name = attribute.get("Name")
            value = attribute.get("Value")

            if not isinstance(value, str):
                continue

            if name == "sub":
                cognito_sub = value
            elif name == "email":
                cognito_email = value

        if cognito_sub is None:
            raise CognitoIdentityValidationError("Cognito AdminGetUser response is missing sub")

        if cognito_email is None:
            raise CognitoIdentityValidationError("Cognito AdminGetUser response is missing email")

        if normalize_email(cognito_email) != normalize_email(expected_email):
            raise CognitoIdentityValidationError(
                "existing Cognito user email does not match expected email"
            )

        return cognito_sub

    def get_verified_user_sub(
        self,
        *,
        user_pool_id: str,
        user_id: str,
        expected_email: str,
        expected_sub: str | None = None,
    ) -> str:
        response = self._client.admin_get_user(
            UserPoolId=user_pool_id,
            Username=user_id,
        )

        if response.get("Username") != user_id:
            raise CognitoIdentityValidationError(
                "Cognito AdminGetUser response username does not match expected username"
            )

        attributes = response.get("UserAttributes")

        if not isinstance(attributes, list):
            raise CognitoIdentityValidationError(
                "Cognito AdminGetUser response is missing UserAttributes"
            )

        cognito_sub: str | None = None
        cognito_email: str | None = None
        email_verified: str | None = None

        for attribute in attributes:
            if not isinstance(attribute, dict):
                continue

            name = attribute.get("Name")
            value = attribute.get("Value")

            if not isinstance(value, str):
                continue

            if name == "sub":
                cognito_sub = value
            elif name == "email":
                cognito_email = value
            elif name == "email_verified":
                email_verified = value

        if cognito_sub is None:
            raise CognitoIdentityValidationError("Cognito AdminGetUser response is missing sub")

        if expected_sub is not None and cognito_sub != expected_sub:
            raise CognitoIdentityValidationError(
                "existing Cognito user sub does not match expected sub"
            )

        if cognito_email is None:
            raise CognitoIdentityValidationError("Cognito AdminGetUser response is missing email")

        if normalize_email(cognito_email) != normalize_email(expected_email):
            raise CognitoIdentityValidationError(
                "existing Cognito user email does not match expected email"
            )

        if email_verified != "true":
            raise CognitoIdentityValidationError("existing Cognito user email is not verified")

        return cognito_sub

    def get_reconciled_user_identity(
        self,
        *,
        user_pool_id: str,
        user_id: str,
        expected_email: str,
        expected_sub: str,
    ) -> ReconciledCognitoIdentity:
        response = self._client.admin_get_user(
            UserPoolId=user_pool_id,
            Username=user_id,
        )

        if response.get("Username") != user_id:
            raise CognitoIdentityValidationError(
                "Cognito AdminGetUser response username does not match expected username"
            )

        attributes = response.get("UserAttributes")
        if not isinstance(attributes, list):
            raise CognitoIdentityValidationError(
                "Cognito AdminGetUser response is missing UserAttributes"
            )

        cognito_sub: str | None = None
        cognito_email: str | None = None
        email_verified: str | None = None

        for attribute in attributes:
            if not isinstance(attribute, dict):
                continue

            name = attribute.get("Name")
            value = attribute.get("Value")
            if name == "email_verified" and not isinstance(value, str):
                raise CognitoIdentityValidationError(
                    "existing Cognito user email_verified value is incompatible"
                )
            if not isinstance(value, str):
                continue

            if name == "sub":
                cognito_sub = value
            elif name == "email":
                cognito_email = value
            elif name == "email_verified":
                email_verified = value

        if cognito_sub is None:
            raise CognitoIdentityValidationError("Cognito AdminGetUser response is missing sub")
        if cognito_sub != expected_sub:
            raise CognitoIdentityValidationError(
                "existing Cognito user sub does not match expected sub"
            )
        if cognito_email is None:
            raise CognitoIdentityValidationError("Cognito AdminGetUser response is missing email")
        if normalize_email(cognito_email) != normalize_email(expected_email):
            raise CognitoIdentityValidationError(
                "existing Cognito user email does not match expected email"
            )
        if email_verified not in {None, "false", "true"}:
            raise CognitoIdentityValidationError(
                "existing Cognito user email_verified value is incompatible"
            )

        return ReconciledCognitoIdentity(
            cognito_sub=cognito_sub,
            verified=email_verified == "true",
        )

    def set_email_verified(self, *, user_pool_id: str, user_id: str) -> None:
        self._client.admin_update_user_attributes(
            UserPoolId=user_pool_id,
            Username=user_id,
            UserAttributes=[
                {
                    "Name": "email_verified",
                    "Value": "true",
                }
            ],
        )

    def delete_user(self, *, user_pool_id: str, user_id: str) -> None:
        self._client.admin_delete_user(
            UserPoolId=user_pool_id,
            Username=user_id,
        )

    def disable_user(self, *, user_pool_id: str, user_id: str) -> None:
        self._client.admin_disable_user(
            UserPoolId=user_pool_id,
            Username=user_id,
        )

    def resend_invitation(self, *, user_pool_id: str, user_id: str) -> None:
        self._client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=user_id,
            MessageAction="RESEND",
        )

from typing import Any, Protocol

from tools.bootstrap_admin.normalization import normalize_email


class CognitoClient(Protocol):
    def admin_create_user(self, **kwargs: object) -> dict[str, Any]: ...

    def admin_get_user(self, **kwargs: object) -> dict[str, Any]: ...

    def admin_delete_user(self, **kwargs: object) -> dict[str, Any]: ...

    def admin_disable_user(self, **kwargs: object) -> dict[str, Any]: ...


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
                }
            ],
            MessageAction="SUPPRESS",
            ForceAliasCreation=False,
        )

        user = response.get("User")

        if not isinstance(user, dict):
            raise RuntimeError("Cognito AdminCreateUser response is missing User")

        attributes = user.get("Attributes")

        if not isinstance(attributes, list):
            raise RuntimeError("Cognito AdminCreateUser response is missing Attributes")

        for attribute in attributes:
            if not isinstance(attribute, dict):
                continue

            if attribute.get("Name") != "sub":
                continue

            value = attribute.get("Value")

            if isinstance(value, str):
                return value

        raise RuntimeError("Cognito AdminCreateUser response is missing sub")

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
            raise RuntimeError("Cognito AdminGetUser response is missing UserAttributes")

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
            raise RuntimeError("Cognito AdminGetUser response is missing sub")

        if cognito_email is None:
            raise RuntimeError("Cognito AdminGetUser response is missing email")

        if normalize_email(cognito_email) != normalize_email(expected_email):
            raise RuntimeError("existing Cognito user email does not match expected email")

        return cognito_sub

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

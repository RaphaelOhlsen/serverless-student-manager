from typing import Any, Protocol


class CognitoClient(Protocol):
    def admin_get_user(self, **kwargs: object) -> dict[str, Any]: ...

    def admin_get_user_auth_factors(self, **kwargs: object) -> dict[str, Any]: ...


class CognitoRepository:
    def __init__(self, client: CognitoClient, user_pool_id: str) -> None:
        self._client = client
        self._user_pool_id = user_pool_id

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

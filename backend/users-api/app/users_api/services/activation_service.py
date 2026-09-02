import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4, uuid5

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from users_api.errors import ActivationConflictError, ActivationForbiddenError


class UserRepositoryProtocol(Protocol):
    def get_authorization(self, cognito_sub: str) -> dict[str, object] | None: ...

    def get_profile(self, user_id: str) -> dict[str, object] | None: ...

    def activate(
        self,
        *,
        user_id: str,
        cognito_sub: str,
        role: str,
        auth_version: int,
        occurred_at: str,
        event_id: str,
        correlation_id: str,
        expires_at: int,
        client_request_token: str,
    ) -> None: ...


class CognitoRepositoryProtocol(Protocol):
    def get_user(self, user_id: str) -> dict[str, Any]: ...

    def get_user_auth_factors(self, user_id: str) -> dict[str, Any]: ...


class IdempotencyRepositoryProtocol(Protocol):
    def start(self, record: dict[str, object]) -> None: ...

    def get(self, record_id: str) -> dict[str, object] | None: ...

    def complete(self, *, record_id: str, response: dict[str, object], updated_at: str) -> None: ...


class ActivationService:
    def __init__(
        self,
        users: UserRepositoryProtocol,
        cognito: CognitoRepositoryProtocol,
        idempotency: IdempotencyRepositoryProtocol,
        *,
        environment: str,
        audit_retention_days: int,
        clock: Callable[[], datetime] | None = None,
        identifier_factory: Callable[[], UUID] | None = None,
    ) -> None:
        self._users = users
        self._cognito = cognito
        self._idempotency = idempotency
        self._environment = environment
        self._audit_retention_days = audit_retention_days
        self._clock = clock or (lambda: datetime.now(UTC))
        self._identifier_factory = identifier_factory or uuid4

    def activate_current_user(
        self,
        *,
        cognito_sub: str,
        idempotency_key: str,
        request_id: str | None,
    ) -> dict[str, object]:
        authorization, profile = self._load_and_reconcile(cognito_sub)
        user_id = self._required_string(authorization, "userId")
        role = self._required_string(authorization, "role")
        status = self._required_string(authorization, "status")
        auth_version = self._required_int(authorization, "authVersion")

        self._validate_cognito(user_id, cognito_sub)

        now = self._clock().astimezone(UTC)
        occurred_at = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        correlation_id = request_id or str(self._identifier_factory())
        event_id = str(self._identifier_factory())
        response = self._response(user_id, role, auth_version)
        record_id = self._record_id(user_id, idempotency_key)
        payload_hash = self._payload_hash(user_id)
        record = {
            "id": record_id,
            "environment": self._environment,
            "actorId": user_id,
            "operation": "activate-current-user",
            "target": user_id,
            "idempotencyKey": idempotency_key,
            "payloadHash": payload_hash,
            "state": "STARTED",
            "eventId": event_id,
            "correlationId": correlation_id,
            "occurredAt": occurred_at,
            "createdAt": occurred_at,
            "updatedAt": occurred_at,
            "expiration": int((now + timedelta(hours=24)).timestamp()),
        }

        try:
            self._idempotency.start(record)
        except ClientError as error:
            if self._error_code(error) != "ConditionalCheckFailedException":
                raise
            return self._replay(
                record_id=record_id,
                payload_hash=payload_hash,
                cognito_sub=cognito_sub,
            )

        if status == "ACTIVE":
            return self._complete_idempotency(
                record_id=record_id,
                response=response,
                updated_at=occurred_at,
            )

        try:
            self._users.activate(
                user_id=user_id,
                cognito_sub=cognito_sub,
                role=role,
                auth_version=auth_version,
                occurred_at=occurred_at,
                event_id=event_id,
                correlation_id=correlation_id,
                expires_at=int((now + timedelta(days=self._audit_retention_days)).timestamp()),
                client_request_token=str(uuid5(UUID(int=0), record_id)),
            )
        except ClientError as error:
            if self._error_code(error) not in {
                "ConditionalCheckFailedException",
                "TransactionCanceledException",
            }:
                raise
            current_authorization, current_profile = self._load_and_reconcile(cognito_sub)
            if not self._both_active(current_authorization, current_profile):
                raise ActivationConflictError from None

        return self._complete_idempotency(
            record_id=record_id,
            response=response,
            updated_at=occurred_at,
        )

    def _replay(
        self,
        *,
        record_id: str,
        payload_hash: str,
        cognito_sub: str,
    ) -> dict[str, object]:
        existing = self._idempotency.get(record_id)
        if existing is None or existing.get("payloadHash") != payload_hash:
            raise ActivationConflictError
        if existing.get("operation") != "activate-current-user":
            raise ActivationConflictError
        if existing.get("state") == "COMPLETED":
            response = existing.get("response")
            if not isinstance(response, dict):
                raise ActivationConflictError
            return response
        if existing.get("state") != "STARTED":
            raise ActivationConflictError

        authorization, profile = self._load_and_reconcile(cognito_sub)
        if not self._both_active(authorization, profile):
            raise ActivationConflictError
        response = self._response(
            self._required_string(authorization, "userId"),
            self._required_string(authorization, "role"),
            self._required_int(authorization, "authVersion"),
        )
        updated_at = (
            self._clock().astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )
        return self._complete_idempotency(
            record_id=record_id,
            response=response,
            updated_at=updated_at,
        )

    def _complete_idempotency(
        self,
        *,
        record_id: str,
        response: dict[str, object],
        updated_at: str,
    ) -> dict[str, object]:
        try:
            self._idempotency.complete(
                record_id=record_id,
                response=response,
                updated_at=updated_at,
            )
            return response
        except ClientError as error:
            if self._error_code(error) != "ConditionalCheckFailedException":
                raise
            existing = self._idempotency.get(record_id)
            preserved = existing.get("response") if existing is not None else None
            if (
                existing is None
                or existing.get("state") != "COMPLETED"
                or preserved != response
                or not isinstance(preserved, dict)
            ):
                raise ActivationConflictError from None
            return preserved

    def _load_and_reconcile(self, cognito_sub: str) -> tuple[dict[str, object], dict[str, object]]:
        authorization = self._users.get_authorization(cognito_sub)
        if authorization is None:
            raise ActivationForbiddenError
        user_id = self._required_string(authorization, "userId")
        profile = self._users.get_profile(user_id)
        if profile is None:
            raise ActivationForbiddenError

        try:
            role = self._required_string(authorization, "role")
            status = self._required_string(authorization, "status")
            auth_version = self._required_int(authorization, "authVersion")
            if role not in {"ADMIN", "OPERATOR"}:
                raise ActivationForbiddenError
            if status not in {"INVITED", "ACTIVE"}:
                raise ActivationConflictError
            if self._required_string(profile, "userId") != user_id:
                raise ActivationForbiddenError
            if self._required_string(profile, "cognitoSub") != cognito_sub:
                raise ActivationForbiddenError
            if self._required_string(profile, "role") != role:
                raise ActivationForbiddenError
            if self._required_string(profile, "status") != status:
                raise ActivationForbiddenError
            if self._required_int(profile, "authVersion") != auth_version:
                raise ActivationForbiddenError
        except (KeyError, TypeError):
            raise ActivationForbiddenError from None
        return authorization, profile

    def _validate_cognito(self, user_id: str, cognito_sub: str) -> None:
        try:
            user = self._cognito.get_user(user_id)
            factors = self._cognito.get_user_auth_factors(user_id)
        except ClientError as error:
            if self._error_code(error) == "UserNotFoundException":
                raise ActivationForbiddenError from None
            raise

        attributes = {
            item.get("Name"): item.get("Value")
            for item in user.get("UserAttributes", [])
            if isinstance(item, dict)
        }
        if user.get("Username") != user_id or factors.get("Username") != user_id:
            raise ActivationForbiddenError
        if attributes.get("sub") != cognito_sub:
            raise ActivationForbiddenError
        if (
            user.get("Enabled") is not True
            or user.get("UserStatus") != "CONFIRMED"
            or attributes.get("email_verified") != "true"
            or "SOFTWARE_TOKEN" not in factors.get("ConfiguredUserAuthFactors", [])
        ):
            raise ActivationConflictError

    @staticmethod
    def _required_string(item: dict[str, object], name: str) -> str:
        value = item.get(name)
        if not isinstance(value, str) or not value:
            raise ActivationForbiddenError
        return value

    @staticmethod
    def _required_int(item: dict[str, object], name: str) -> int:
        value = item.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ActivationForbiddenError
        return value

    @staticmethod
    def _both_active(authorization: dict[str, object], profile: dict[str, object]) -> bool:
        return authorization.get("status") == "ACTIVE" and profile.get("status") == "ACTIVE"

    def _record_id(self, user_id: str, key: str) -> str:
        return f"HTTP#{self._environment}#{user_id}#activate-current-user#{key}"

    @staticmethod
    def _payload_hash(user_id: str) -> str:
        payload = json.dumps(
            {"operation": "activate-current-user", "userId": user_id},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _response(user_id: str, role: str, auth_version: int) -> dict[str, object]:
        return {
            "userId": user_id,
            "role": role,
            "status": "ACTIVE",
            "authVersion": auth_version,
        }

    @staticmethod
    def _error_code(error: ClientError) -> str:
        return str(error.response.get("Error", {}).get("Code", ""))

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4, uuid5

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from users_api.errors import ActivationConflictError, ActivationForbiddenError
from users_api.services.user_state import (
    UserStateReconciliationError,
    UserStateRepositoryProtocol,
    reconcile_user_state,
)


class UserRepositoryProtocol(UserStateRepositoryProtocol, Protocol):
    def activate(
        self,
        *,
        user_id: str,
        cognito_sub: str,
        role: str,
        version: int,
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
        version = self._logical_profile_version(profile)

        self._validate_cognito(user_id, cognito_sub)

        record_id = self._record_id(user_id, idempotency_key)
        payload_hash = self._payload_hash(user_id)
        existing = self._idempotency.get(record_id)
        if existing is not None:
            return self._replay(
                existing=existing,
                record_id=record_id,
                payload_hash=payload_hash,
                cognito_sub=cognito_sub,
                idempotency_key=idempotency_key,
                user_id=user_id,
            )

        now = self._clock().astimezone(UTC)
        occurred_at = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        correlation_id = request_id or str(self._identifier_factory())
        event_id = str(self._identifier_factory())
        next_version = version + 1 if status == "INVITED" else version
        next_auth_version = auth_version + 1 if status == "INVITED" else auth_version
        response = self._response(user_id, role, next_auth_version)
        record = {
            "id": record_id,
            "environment": self._environment,
            "actorId": user_id,
            "operation": "activate-current-user",
            "target": user_id,
            "idempotencyKey": idempotency_key,
            "payloadHash": payload_hash,
            "state": "STARTED",
            "sourceStatus": status,
            "profileVersion": version,
            "authVersion": auth_version,
            "nextProfileVersion": next_version,
            "nextAuthVersion": next_auth_version,
            "response": response,
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
                existing=None,
                record_id=record_id,
                payload_hash=payload_hash,
                cognito_sub=cognito_sub,
                idempotency_key=idempotency_key,
                user_id=user_id,
            )

        if status == "ACTIVE":
            return self._complete_idempotency(
                record_id=record_id,
                response=response,
                updated_at=occurred_at,
            )

        return self._activate_and_complete(
            record_id=record_id,
            cognito_sub=cognito_sub,
            user_id=user_id,
            role=role,
            version=version,
            auth_version=auth_version,
            occurred_at=occurred_at,
            event_id=event_id,
            correlation_id=correlation_id,
            audit_expires_at=int((now + timedelta(days=self._audit_retention_days)).timestamp()),
            response=response,
        )

    def _replay(
        self,
        *,
        existing: dict[str, object] | None,
        record_id: str,
        payload_hash: str,
        cognito_sub: str,
        idempotency_key: str,
        user_id: str,
    ) -> dict[str, object]:
        if existing is None:
            existing = self._idempotency.get(record_id)
        if existing is None or not self._same_context(
            existing,
            record_id=record_id,
            payload_hash=payload_hash,
            idempotency_key=idempotency_key,
            user_id=user_id,
        ):
            raise ActivationConflictError
        if existing.get("state") == "COMPLETED":
            response = existing.get("response")
            if not isinstance(response, dict):
                raise ActivationConflictError
            return response
        if existing.get("state") != "STARTED":
            raise ActivationConflictError

        authorization, profile = self._load_and_reconcile(cognito_sub)
        user_id = self._required_string(authorization, "userId")
        role = self._required_string(authorization, "role")
        status = self._required_string(authorization, "status")
        auth_version = self._required_int(authorization, "authVersion")
        version = self._logical_profile_version(profile)
        source_status = self._started_string(existing, "sourceStatus")
        expected_version = self._started_int(existing, "profileVersion")
        expected_auth_version = self._started_int(existing, "authVersion")
        next_version = self._started_int(existing, "nextProfileVersion")
        next_auth_version = self._started_int(existing, "nextAuthVersion")
        response = existing.get("response")
        if not isinstance(response, dict):
            raise ActivationConflictError
        if source_status == "INVITED":
            if (
                next_version != expected_version + 1
                or next_auth_version != expected_auth_version + 1
                or response != self._response(user_id, role, next_auth_version)
            ):
                raise ActivationConflictError
        elif source_status == "ACTIVE":
            if (
                next_version != expected_version
                or next_auth_version != expected_auth_version
                or response != self._response(user_id, role, expected_auth_version)
            ):
                raise ActivationConflictError
        else:
            raise ActivationConflictError

        occurred_at = self._required_string(existing, "occurredAt")
        if self._matches_state(
            status=status,
            version=version,
            auth_version=auth_version,
            expected_status="ACTIVE",
            expected_version=next_version,
            expected_auth_version=next_auth_version,
        ):
            return self._complete_idempotency(
                record_id=record_id,
                response=response,
                updated_at=occurred_at,
            )

        if not self._matches_state(
            status=status,
            version=version,
            auth_version=auth_version,
            expected_status=source_status,
            expected_version=expected_version,
            expected_auth_version=expected_auth_version,
        ):
            raise ActivationConflictError
        if source_status == "ACTIVE":
            return self._complete_idempotency(
                record_id=record_id,
                response=response,
                updated_at=occurred_at,
            )

        return self._activate_and_complete(
            record_id=record_id,
            cognito_sub=cognito_sub,
            user_id=user_id,
            role=role,
            version=expected_version,
            auth_version=expected_auth_version,
            occurred_at=occurred_at,
            event_id=self._required_string(existing, "eventId"),
            correlation_id=self._required_string(existing, "correlationId"),
            audit_expires_at=self._audit_expires_at(occurred_at),
            response=response,
        )

    def _activate_and_complete(
        self,
        *,
        record_id: str,
        cognito_sub: str,
        user_id: str,
        role: str,
        version: int,
        auth_version: int,
        occurred_at: str,
        event_id: str,
        correlation_id: str,
        audit_expires_at: int,
        response: dict[str, object],
    ) -> dict[str, object]:
        try:
            self._users.activate(
                user_id=user_id,
                cognito_sub=cognito_sub,
                role=role,
                version=version,
                auth_version=auth_version,
                occurred_at=occurred_at,
                event_id=event_id,
                correlation_id=correlation_id,
                expires_at=audit_expires_at,
                client_request_token=str(uuid5(UUID(int=0), record_id)),
            )
        except ClientError as error:
            if self._error_code(error) not in {
                "ConditionalCheckFailedException",
                "TransactionCanceledException",
            }:
                raise
            current_authorization, current_profile = self._load_and_reconcile(cognito_sub)
            current_version = self._logical_profile_version(current_profile)
            current_auth_version = self._required_int(current_authorization, "authVersion")
            if not self._matches_state(
                status=self._required_string(current_authorization, "status"),
                version=current_version,
                auth_version=current_auth_version,
                expected_status="ACTIVE",
                expected_version=version + 1,
                expected_auth_version=auth_version + 1,
            ):
                raise ActivationConflictError from None

        return self._complete_idempotency(
            record_id=record_id,
            response=response,
            updated_at=occurred_at,
        )

    def _same_context(
        self,
        existing: dict[str, object],
        *,
        record_id: str,
        payload_hash: str,
        idempotency_key: str,
        user_id: str,
    ) -> bool:
        return (
            existing.get("id") == record_id
            and existing.get("environment") == self._environment
            and existing.get("actorId") == user_id
            and existing.get("target") == user_id
            and existing.get("operation") == "activate-current-user"
            and existing.get("idempotencyKey") == idempotency_key
            and existing.get("payloadHash") == payload_hash
        )

    def _audit_expires_at(self, occurred_at: str) -> int:
        try:
            timestamp = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        except ValueError:
            raise ActivationConflictError from None
        if timestamp.tzinfo is None or not occurred_at.endswith("Z"):
            raise ActivationConflictError
        return int((timestamp + timedelta(days=self._audit_retention_days)).timestamp())

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
        try:
            state = reconcile_user_state(
                self._users,
                cognito_sub,
                self._validate_activation_authorization,
            )
        except UserStateReconciliationError:
            raise ActivationForbiddenError from None
        return (
            {
                "userId": state.user_id,
                "role": state.role,
                "status": state.status,
                "authVersion": state.auth_version,
            },
            state.profile,
        )

    @staticmethod
    def _validate_activation_authorization(role: str, status: str, auth_version: int) -> None:
        if role not in {"ADMIN", "OPERATOR"}:
            raise ActivationForbiddenError
        if status not in {"INVITED", "ACTIVE"}:
            raise ActivationConflictError

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
    def _logical_profile_version(profile: dict[str, object]) -> int:
        if "version" not in profile:
            return 1
        return ActivationService._required_int(profile, "version")

    @staticmethod
    def _started_string(record: dict[str, object], name: str) -> str:
        value = record.get(name)
        if not isinstance(value, str) or not value:
            raise ActivationConflictError
        return value

    @staticmethod
    def _started_int(record: dict[str, object], name: str) -> int:
        value = record.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ActivationConflictError
        return value

    @staticmethod
    def _matches_state(
        *,
        status: str,
        version: int,
        auth_version: int,
        expected_status: str,
        expected_version: int,
        expected_auth_version: int,
    ) -> bool:
        return (
            status == expected_status
            and version == expected_version
            and auth_version == expected_auth_version
        )

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

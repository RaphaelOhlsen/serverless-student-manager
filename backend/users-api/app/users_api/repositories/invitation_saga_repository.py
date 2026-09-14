from collections.abc import Callable, Mapping
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

from boto3.dynamodb.types import TypeSerializer  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from users_api.errors import (
    IdempotencyKeyReusedError,
    InvitationSagaConcurrentTransitionError,
    InvitationSagaInvariantError,
    OperationInProgressError,
)
from users_api.repositories.dynamodb_values import normalize_dynamodb_value
from users_api.services.invitation_saga import (
    CHANGE_USER_ROLE_OPERATION,
    CREATE_USER_OPERATION,
    IDEMPOTENCY_TTL_SECONDS,
    IN_PROGRESS_TTL_SECONDS,
    INVITATION_DELIVERY_FAILED,
    INVITATION_DELIVERY_UNCERTAIN,
    RESEND_INVITATION_OPERATION,
    CognitoIdentityEvidence,
    CognitoReconciliationReason,
    CreateSagaState,
    ResendSagaState,
    RoleChangeState,
    SagaClaim,
    create_request_hash,
    resend_request_hash,
    role_change_request_hash,
    validate_transition,
)
from users_api.validation import validate_idempotency_key


class IdempotencyTable(Protocol):
    def put_item(self, **kwargs: object) -> dict[str, Any]: ...

    def get_item(self, **kwargs: object) -> dict[str, Any]: ...

    def update_item(self, **kwargs: object) -> dict[str, Any]: ...


class InvitationSagaRepository:
    def __init__(
        self,
        table: IdempotencyTable,
        table_name: str,
        *,
        clock: Callable[[], float],
        identifier_factory: Callable[[], UUID] | None = None,
    ) -> None:
        self._table = table
        self._table_name = table_name
        self._clock = clock
        self._identifier_factory = identifier_factory or uuid4
        self._serializer = TypeSerializer()

    def claim_create(
        self,
        *,
        environment: str,
        actor_id: str,
        idempotency_key: str,
        full_name: str,
        email: str,
        role: str,
        request_id: str | None,
    ) -> SagaClaim:
        validate_idempotency_key(idempotency_key)
        record_id = self._record_id(environment, actor_id, CREATE_USER_OPERATION, idempotency_key)
        request_hash = create_request_hash(full_name=full_name, email=email, role=role)
        existing = self.get(record_id)
        attempted_context: dict[str, object] = {
            "id": record_id,
            "environment": environment,
            "actorId": actor_id,
            "operation": CREATE_USER_OPERATION,
            "idempotencyKey": idempotency_key,
            "requestHash": request_hash,
        }
        if existing is not None:
            return self._resolve_existing(existing, attempted_context)
        now = self._now_seconds()
        user_id = str(self._identifier_factory())
        event_id = str(self._identifier_factory())
        correlation_id = request_id or str(self._identifier_factory())
        timestamp = self._timestamp(now)
        record: dict[str, object] = {
            "id": record_id,
            "environment": environment,
            "actorId": actor_id,
            "operation": CREATE_USER_OPERATION,
            "target": user_id,
            "idempotencyKey": idempotency_key,
            "requestHash": request_hash,
            "state": CreateSagaState.CLAIMED.value,
            "userId": user_id,
            "eventId": event_id,
            "correlationId": correlation_id,
            "startedAt": timestamp,
            "updatedAt": timestamp,
            "expiration": now + IDEMPOTENCY_TTL_SECONDS,
            "inProgressExpiration": (now + IN_PROGRESS_TTL_SECONDS) * 1000,
        }
        return self._create_or_resolve(record)

    def claim_resend(
        self,
        *,
        environment: str,
        actor_id: str,
        idempotency_key: str,
        user_id: str,
        expected_version: int,
        request_id: str | None,
    ) -> SagaClaim:
        validate_idempotency_key(idempotency_key)
        record_id = self._record_id(
            environment, actor_id, RESEND_INVITATION_OPERATION, idempotency_key
        )
        request_hash = resend_request_hash(user_id=user_id, expected_version=expected_version)
        existing = self.get(record_id)
        attempted_context: dict[str, object] = {
            "id": record_id,
            "environment": environment,
            "actorId": actor_id,
            "operation": RESEND_INVITATION_OPERATION,
            "idempotencyKey": idempotency_key,
            "requestHash": request_hash,
        }
        if existing is not None:
            return self._resolve_existing(existing, attempted_context)
        now = self._now_seconds()
        event_id = str(self._identifier_factory())
        correlation_id = request_id or str(self._identifier_factory())
        timestamp = self._timestamp(now)
        record: dict[str, object] = {
            "id": record_id,
            "environment": environment,
            "actorId": actor_id,
            "operation": RESEND_INVITATION_OPERATION,
            "target": user_id,
            "idempotencyKey": idempotency_key,
            "requestHash": request_hash,
            "state": ResendSagaState.CLAIMED.value,
            "eventId": event_id,
            "correlationId": correlation_id,
            "expectedVersion": expected_version,
            "startedAt": timestamp,
            "updatedAt": timestamp,
            "expiration": now + IDEMPOTENCY_TTL_SECONDS,
            "inProgressExpiration": (now + IN_PROGRESS_TTL_SECONDS) * 1000,
        }
        return self._create_or_resolve(record)

    def claim_role_change(
        self,
        *,
        environment: str,
        actor_id: str,
        idempotency_key: str,
        user_id: str,
        role: str,
        expected_version: int,
        request_id: str | None,
    ) -> SagaClaim:
        validate_idempotency_key(idempotency_key)
        record_id = self._record_id(
            environment, actor_id, CHANGE_USER_ROLE_OPERATION, idempotency_key
        )
        request_hash = role_change_request_hash(
            user_id=user_id, role=role, expected_version=expected_version
        )
        attempted_context: dict[str, object] = {
            "id": record_id,
            "environment": environment,
            "actorId": actor_id,
            "operation": CHANGE_USER_ROLE_OPERATION,
            "idempotencyKey": idempotency_key,
            "requestHash": request_hash,
        }
        existing = self.get(record_id)
        if existing is not None:
            return self._resolve_existing(existing, attempted_context)
        now = self._now_seconds()
        timestamp = self._timestamp(now)
        record: dict[str, object] = {
            **attempted_context,
            "target": user_id,
            "state": RoleChangeState.CLAIMED.value,
            "desiredRole": role,
            "expectedVersion": expected_version,
            "eventId": str(self._identifier_factory()),
            "correlationId": request_id or str(self._identifier_factory()),
            "startedAt": timestamp,
            "updatedAt": timestamp,
            "expiration": now + IDEMPOTENCY_TTL_SECONDS,
            "inProgressExpiration": (now + IN_PROGRESS_TTL_SECONDS) * 1000,
        }
        return self._create_or_resolve(record)

    def transition(self, *, record: dict[str, object], next_state: str) -> None:
        record_id, operation, current_state, request_hash = self._transition_context(record)
        if (
            operation == CREATE_USER_OPERATION
            and current_state == CreateSagaState.CLAIMED.value
            and next_state == CreateSagaState.COGNITO_CREATED.value
        ):
            raise InvitationSagaInvariantError(
                "COGNITO_CREATED requires a reconciled identity transition"
            )
        validate_transition(operation=operation, current_state=current_state, next_state=next_state)
        now = self._now_seconds()
        retrying_delivery = current_state in {
            CreateSagaState.INVITATION_RETRYABLE.value,
            ResendSagaState.RETRYABLE.value,
        }
        update_expression = (
            "SET #state = :next, updatedAt = :updated, inProgressExpiration = :lease"
        )
        if retrying_delivery:
            update_expression += " REMOVE errorCode, httpStatus"
        try:
            self._table.update_item(
                Key={"id": record_id},
                UpdateExpression=update_expression,
                ConditionExpression="#state = :current AND requestHash = :request_hash",
                ExpressionAttributeNames={"#state": "state"},
                ExpressionAttributeValues={
                    ":current": current_state,
                    ":next": next_state,
                    ":request_hash": request_hash,
                    ":updated": self._timestamp(now),
                    ":lease": (now + IN_PROGRESS_TTL_SECONDS) * 1000,
                },
            )
        except ClientError as error:
            if self._error_code(error) == "ConditionalCheckFailedException":
                self._raise_cas_error(
                    record_id=record_id,
                    request_hash=request_hash,
                    next_state=next_state,
                )
            raise

    def store_cognito_created(
        self,
        *,
        record: dict[str, object],
        cognito_sub: str,
        evidence: CognitoIdentityEvidence,
    ) -> None:
        _, operation, current_state, _ = self._transition_context(record)
        if (
            operation != CREATE_USER_OPERATION
            or current_state != CreateSagaState.CLAIMED.value
            or not self._is_canonical_uuid(cognito_sub)
        ):
            raise InvitationSagaInvariantError("invalid reconciled Cognito identity transition")
        self._state_update(
            record=record,
            next_state=CreateSagaState.COGNITO_CREATED.value,
            assignments={"cognitoSub": cognito_sub, "cognitoEvidence": evidence.value},
        )

    def store_cognito_reconciliation_required(
        self,
        *,
        record: dict[str, object],
        reason: CognitoReconciliationReason,
    ) -> None:
        _, operation, current_state, _ = self._transition_context(record)
        if operation != CREATE_USER_OPERATION or current_state != CreateSagaState.CLAIMED.value:
            raise InvitationSagaInvariantError("invalid Cognito reconciliation transition")
        self._state_update(
            record=record,
            next_state=CreateSagaState.RECONCILIATION_REQUIRED.value,
            assignments={"errorCode": reason.value},
        )

    def build_transaction_transition(
        self,
        *,
        record: dict[str, object],
        next_state: str,
    ) -> dict[str, object]:
        record_id, operation, current_state, request_hash = self._transition_context(record)
        if (
            operation != CREATE_USER_OPERATION
            or current_state != CreateSagaState.COGNITO_CREATED.value
            or next_state != CreateSagaState.DDB_COMMITTED.value
        ):
            raise InvitationSagaInvariantError(
                "transaction hook is restricted to create DDB_COMMITTED"
            )
        validate_transition(operation=operation, current_state=current_state, next_state=next_state)
        started_at = record.get("startedAt")
        if not isinstance(started_at, str) or not started_at:
            raise InvitationSagaInvariantError("transaction hook requires stable startedAt")
        values: dict[str, object] = {
            ":current": current_state,
            ":next": next_state,
            ":request_hash": request_hash,
            ":updated": started_at,
        }
        return {
            "Update": {
                "TableName": self._table_name,
                "Key": self._serialize({"id": record_id}),
                "UpdateExpression": "SET #state = :next, updatedAt = :updated",
                "ConditionExpression": "#state = :current AND requestHash = :request_hash",
                "ExpressionAttributeNames": {"#state": "state"},
                "ExpressionAttributeValues": self._serialize(values),
            }
        }

    def build_resend_completion_transition(
        self,
        *,
        record: dict[str, object],
    ) -> dict[str, object]:
        record_id, operation, current_state, request_hash = self._transition_context(record)
        if operation != RESEND_INVITATION_OPERATION or current_state != ResendSagaState.SENT.value:
            raise InvitationSagaInvariantError(
                "transaction hook is restricted to resend completion"
            )
        started_at = record.get("startedAt")
        if not isinstance(started_at, str) or not started_at:
            raise InvitationSagaInvariantError("resend completion requires stable startedAt")
        return {
            "Update": {
                "TableName": self._table_name,
                "Key": self._serialize({"id": record_id}),
                "UpdateExpression": (
                    "SET #state = :completed, httpStatus = :status, updatedAt = :updated"
                ),
                "ConditionExpression": "#state = :sent AND requestHash = :request_hash",
                "ExpressionAttributeNames": {"#state": "state"},
                "ExpressionAttributeValues": self._serialize(
                    {
                        ":sent": ResendSagaState.SENT.value,
                        ":completed": ResendSagaState.COMPLETED.value,
                        ":status": 204,
                        ":request_hash": request_hash,
                        ":updated": started_at,
                    }
                ),
            }
        }

    def build_role_change_completion_transition(
        self,
        *,
        record: dict[str, object],
        response: dict[str, object],
    ) -> dict[str, object]:
        record_id, operation, current_state, request_hash = self._transition_context(record)
        if operation != CHANGE_USER_ROLE_OPERATION or current_state != RoleChangeState.CLAIMED:
            raise InvitationSagaInvariantError(
                "transaction hook is restricted to role change completion"
            )
        fields = {
            "responseUserId": response.get("userId"),
            "responseRole": response.get("role"),
            "responseStatus": response.get("status"),
            "responseVersion": response.get("version"),
            "responseCreatedAt": response.get("createdAt"),
            "responseUpdatedAt": response.get("updatedAt"),
        }
        started_at = record.get("startedAt")
        if (
            not all(
                isinstance(value, str) and value
                for name, value in fields.items()
                if name != "responseVersion"
            )
            or type(fields["responseVersion"]) is not int
            or fields["responseVersion"] < 1
            or fields["responseUserId"] != record.get("target")
            or fields["responseRole"] != record.get("desiredRole")
            or not isinstance(started_at, str)
            or not started_at
        ):
            raise InvitationSagaInvariantError("role change completion response is invalid")
        names = {"#state": "state"}
        values: dict[str, object] = {
            ":claimed": RoleChangeState.CLAIMED.value,
            ":completed": RoleChangeState.COMPLETED.value,
            ":request_hash": request_hash,
            ":status": 200,
            ":updated": started_at,
        }
        assignments = ["#state = :completed", "httpStatus = :status", "updatedAt = :updated"]
        for index, (name, value) in enumerate(fields.items()):
            names[f"#field{index}"] = name
            values[f":value{index}"] = value
            assignments.append(f"#field{index} = :value{index}")
        return {
            "Update": {
                "TableName": self._table_name,
                "Key": self._serialize({"id": record_id}),
                "UpdateExpression": f"SET {', '.join(assignments)}",
                "ConditionExpression": "#state = :claimed AND requestHash = :request_hash",
                "ExpressionAttributeNames": names,
                "ExpressionAttributeValues": self._serialize(values),
            }
        }

    def begin_cognito_compensation(
        self,
        *,
        record: dict[str, object],
        http_status: int,
        error_code: str,
    ) -> None:
        if http_status not in {409, 500} or not error_code:
            raise InvitationSagaInvariantError("invalid compensation terminal result")
        self._state_update(
            record=record,
            next_state=CreateSagaState.COMPENSATING.value,
            assignments={"terminalHttpStatus": http_status, "terminalErrorCode": error_code},
        )

    def complete_compensation(self, *, record: dict[str, object]) -> None:
        status = record.get("terminalHttpStatus")
        error_code = record.get("terminalErrorCode")
        if type(status) is not int or status not in {409, 500}:
            raise InvitationSagaInvariantError("compensation is missing terminal HTTP status")
        if not isinstance(error_code, str) or not error_code:
            raise InvitationSagaInvariantError("compensation is missing terminal error code")
        self._state_update(
            record=record,
            next_state=CreateSagaState.COMPLETED.value,
            assignments={"httpStatus": status, "errorCode": error_code},
        )

    def store_provisioning_reconciliation_required(
        self,
        *,
        record: dict[str, object],
        reason: str,
    ) -> None:
        if not reason:
            raise InvitationSagaInvariantError("provisioning reconciliation reason is required")
        self._state_update(
            record=record,
            next_state=CreateSagaState.RECONCILIATION_REQUIRED.value,
            assignments={"errorCode": reason},
        )

    def store_completed(
        self,
        *,
        record: dict[str, object],
        http_status: int,
        response_user_id: str | None = None,
    ) -> None:
        if http_status == 201:
            if not response_user_id:
                raise InvitationSagaInvariantError("create completion requires response user ID")
        elif http_status == 204:
            if response_user_id is not None:
                raise InvitationSagaInvariantError("resend completion cannot store response")
        else:
            raise InvitationSagaInvariantError("unsupported invitation completion status")
        self._state_update(
            record=record,
            next_state="COMPLETED",
            assignments={
                "httpStatus": http_status,
                **({"responseUserId": response_user_id} if response_user_id else {}),
            },
        )

    def store_delivery_failure(
        self,
        *,
        record: dict[str, object],
        retryable_state: str,
        error_code: str,
    ) -> None:
        _, operation, current_state, _ = self._transition_context(record)
        valid_dispatch = (
            operation == CREATE_USER_OPERATION
            and current_state == CreateSagaState.INVITATION_DISPATCHING.value
            and retryable_state
            in {
                CreateSagaState.INVITATION_RETRYABLE.value,
                CreateSagaState.RECONCILIATION_REQUIRED.value,
            }
        ) or (
            operation == RESEND_INVITATION_OPERATION
            and current_state == ResendSagaState.DISPATCHING.value
            and retryable_state
            in {
                ResendSagaState.RETRYABLE.value,
                ResendSagaState.RECONCILIATION_REQUIRED.value,
            }
        )
        if not valid_dispatch:
            raise InvitationSagaInvariantError("delivery failure requires a dispatching state")
        expected_code = (
            INVITATION_DELIVERY_UNCERTAIN
            if retryable_state == "RECONCILIATION_REQUIRED"
            else INVITATION_DELIVERY_FAILED
        )
        if error_code != expected_code:
            raise InvitationSagaInvariantError("delivery failure state and code mismatch")
        self._state_update(
            record=record,
            next_state=retryable_state,
            assignments={"httpStatus": 503, "errorCode": error_code},
        )

    def _state_update(
        self,
        *,
        record: dict[str, object],
        next_state: str,
        assignments: dict[str, object],
    ) -> None:
        record_id, operation, current_state, request_hash = self._transition_context(record)
        validate_transition(operation=operation, current_state=current_state, next_state=next_state)
        names = {"#state": "state"}
        values: dict[str, object] = {
            ":current": current_state,
            ":next": next_state,
            ":request_hash": request_hash,
            ":updated": self._timestamp(self._now_seconds()),
        }
        updates = ["#state = :next", "updatedAt = :updated"]
        for index, (name, value) in enumerate(assignments.items()):
            name_key = f"#field{index}"
            value_key = f":value{index}"
            names[name_key] = name
            values[value_key] = value
            updates.append(f"{name_key} = {value_key}")
        try:
            self._table.update_item(
                Key={"id": record_id},
                UpdateExpression=f"SET {', '.join(updates)}",
                ConditionExpression="#state = :current AND requestHash = :request_hash",
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
            )
        except ClientError as error:
            if self._error_code(error) == "ConditionalCheckFailedException":
                self._raise_cas_error(
                    record_id=record_id,
                    request_hash=request_hash,
                    next_state=next_state,
                )
            raise

    def _raise_cas_error(
        self,
        *,
        record_id: str,
        request_hash: str,
        next_state: str,
    ) -> None:
        current = self.get(record_id)
        if (
            current is not None
            and current.get("requestHash") == request_hash
            and current.get("state") == next_state
        ):
            raise InvitationSagaConcurrentTransitionError(
                "invitation saga transition was completed concurrently"
            ) from None
        raise InvitationSagaInvariantError("invitation saga CAS mismatch") from None

    def _create_or_resolve(self, attempted: dict[str, object]) -> SagaClaim:
        try:
            self._table.put_item(
                Item=attempted,
                ConditionExpression="attribute_not_exists(id)",
            )
            return SagaClaim(attempted, created=True)
        except ClientError as error:
            if self._error_code(error) != "ConditionalCheckFailedException":
                raise
        existing = self.get(str(attempted["id"]))
        if existing is None:
            raise InvitationSagaInvariantError("idempotency claim disappeared")
        return self._resolve_existing(existing, attempted)

    def _resolve_existing(
        self,
        existing: dict[str, object],
        attempted: dict[str, object],
    ) -> SagaClaim:
        for field in ("id", "environment", "actorId", "operation", "idempotencyKey"):
            if existing.get(field) != attempted.get(field):
                raise InvitationSagaInvariantError("idempotency claim context mismatch")
        if existing.get("requestHash") != attempted.get("requestHash"):
            raise IdempotencyKeyReusedError
        self._validate_existing_record(existing)
        state = existing.get("state")
        if state in {"COMPLETED", "RECONCILIATION_REQUIRED", "INVITATION_RETRYABLE", "RETRYABLE"}:
            return SagaClaim(existing, created=False)
        lease = existing.get("inProgressExpiration")
        if type(lease) is not int:
            raise InvitationSagaInvariantError("idempotency claim lease is invalid")
        now_millis = self._now_seconds() * 1000
        if lease > now_millis:
            raise OperationInProgressError
        self._renew_lease(existing, now_millis)
        renewed = self.get(str(existing["id"]))
        if renewed is None:
            raise InvitationSagaInvariantError("renewed idempotency claim disappeared")
        return SagaClaim(renewed, created=False)

    @staticmethod
    def _validate_existing_record(record: dict[str, object]) -> None:
        operation = record.get("operation")
        state = record.get("state")
        common_strings = ("target", "eventId", "correlationId", "startedAt")
        if any(
            not isinstance(record.get(field), str) or not record[field] for field in common_strings
        ):
            raise InvitationSagaInvariantError("idempotency claim has invalid durable identifiers")
        if type(record.get("expiration")) is not int:
            raise InvitationSagaInvariantError("idempotency claim TTL is invalid")
        try:
            if operation == CREATE_USER_OPERATION:
                create_state = CreateSagaState(str(state))
                user_id = record.get("userId")
                event_id = record.get("eventId")
                if (
                    not isinstance(user_id, str)
                    or record.get("target") != user_id
                    or not InvitationSagaRepository._is_canonical_uuid(user_id)
                    or not isinstance(event_id, str)
                    or not InvitationSagaRepository._is_canonical_uuid(event_id)
                ):
                    raise InvitationSagaInvariantError(
                        "create-user claim has invalid stable identifiers"
                    )
                if create_state in {
                    CreateSagaState.COGNITO_CREATED,
                    CreateSagaState.COMPENSATING,
                    CreateSagaState.DDB_COMMITTED,
                    CreateSagaState.INVITATION_DISPATCHING,
                    CreateSagaState.INVITATION_RETRYABLE,
                    CreateSagaState.INVITATION_SENT,
                    CreateSagaState.COMPLETED,
                }:
                    cognito_sub = record.get("cognitoSub")
                    evidence = record.get("cognitoEvidence")
                    if (
                        not isinstance(cognito_sub, str)
                        or not InvitationSagaRepository._is_canonical_uuid(cognito_sub)
                        or evidence not in {item.value for item in CognitoIdentityEvidence}
                    ):
                        raise InvitationSagaInvariantError(
                            "create-user claim has invalid Cognito identity evidence"
                        )
                return
            if operation == RESEND_INVITATION_OPERATION:
                ResendSagaState(str(state))
                expected_version = record.get("expectedVersion")
                if type(expected_version) is not int or expected_version < 1:
                    raise InvitationSagaInvariantError(
                        "resend invitation claim has invalid expected version"
                    )
                return
            if operation == CHANGE_USER_ROLE_OPERATION:
                RoleChangeState(str(state))
                expected_version = record.get("expectedVersion")
                desired_role = record.get("desiredRole")
                if (
                    type(expected_version) is not int
                    or expected_version < 1
                    or desired_role not in {"ADMIN", "OPERATOR"}
                ):
                    raise InvitationSagaInvariantError("role change claim is invalid")
                if state == RoleChangeState.COMPLETED.value and record.get("httpStatus") != 200:
                    raise InvitationSagaInvariantError("role change replay status is invalid")
                return
        except ValueError:
            raise InvitationSagaInvariantError("idempotency claim has unknown state") from None
        raise InvitationSagaInvariantError("idempotency claim has unsupported operation")

    def _renew_lease(self, record: dict[str, object], now_millis: int) -> None:
        try:
            self._table.update_item(
                Key={"id": record["id"]},
                UpdateExpression="SET inProgressExpiration = :lease",
                ConditionExpression=(
                    "#state = :state AND requestHash = :request_hash "
                    "AND inProgressExpiration <= :now"
                ),
                ExpressionAttributeNames={"#state": "state"},
                ExpressionAttributeValues={
                    ":state": record["state"],
                    ":request_hash": record["requestHash"],
                    ":now": now_millis,
                    ":lease": now_millis + IN_PROGRESS_TTL_SECONDS * 1000,
                },
            )
        except ClientError as error:
            if self._error_code(error) == "ConditionalCheckFailedException":
                raise OperationInProgressError from None
            raise

    def get(self, record_id: str) -> dict[str, object] | None:
        response = self._table.get_item(Key={"id": record_id}, ConsistentRead=True)
        normalized = normalize_dynamodb_value(response.get("Item"))
        return normalized if isinstance(normalized, dict) else None

    @staticmethod
    def _transition_context(record: dict[str, object]) -> tuple[str, str, str, str]:
        values = tuple(record.get(name) for name in ("id", "operation", "state", "requestHash"))
        if not all(isinstance(value, str) and value for value in values):
            raise InvitationSagaInvariantError("invalid invitation saga transition context")
        record_id, operation, state, request_hash = cast(tuple[str, str, str, str], values)
        return record_id, operation, state, request_hash

    @staticmethod
    def _record_id(environment: str, actor_id: str, operation: str, key: str) -> str:
        return f"HTTP#{environment}#{actor_id}#{operation}#{key}"

    @staticmethod
    def _is_canonical_uuid(value: str) -> bool:
        try:
            return str(UUID(value)) == value
        except ValueError:
            return False

    def _now_seconds(self) -> int:
        return int(self._clock())

    @staticmethod
    def _timestamp(epoch_seconds: int) -> str:
        from datetime import UTC, datetime

        return (
            datetime.fromtimestamp(epoch_seconds, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    def _serialize(self, values: Mapping[str, object]) -> dict[str, object]:
        return {name: self._serializer.serialize(value) for name, value in values.items()}

    @staticmethod
    def _error_code(error: ClientError) -> str:
        return str(error.response.get("Error", {}).get("Code", ""))

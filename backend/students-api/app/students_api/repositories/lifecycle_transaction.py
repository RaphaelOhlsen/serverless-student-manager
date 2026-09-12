"""Build one effective lifecycle transaction; orchestration belongs to the service."""

import json
from dataclasses import dataclass, field
from typing import Any

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from students_api.errors import (
    StudentLifecycleConditionError,
    StudentLifecycleInvariantError,
    StudentLifecycleUnresolvedError,
)
from students_api.repositories.update_transaction import PUBLIC_FIELDS, serialize


@dataclass(frozen=True)
class LifecycleAuditEvent:
    actor_id: str
    correlation_id: str
    event_id: str
    occurred_at: str
    audit_expires_at: int
    reason: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class LifecycleIdempotencyCompletion:
    """Identity is pre-scoped by environment, actor, operation and key."""

    idempotency_id: str
    request_hash: str
    client_request_token: str


@dataclass(frozen=True)
class LifecycleTransition:
    student_id: str
    expected_version: int
    source_status: str
    target_status: str
    public_response: dict[str, object]
    audit_event: LifecycleAuditEvent
    idempotency: LifecycleIdempotencyCompletion


def build_lifecycle_transaction(
    transition: LifecycleTransition,
    *,
    students_table: str,
    audit_table: str,
    idempotency_table: str,
) -> list[dict[str, Any]]:
    """Build the atomic write for an already-decided effective transition."""
    event_type = _validate_transition(
        transition,
        students_table=students_table,
        audit_table=audit_table,
        idempotency_table=idempotency_table,
    )
    audit_event = transition.audit_event
    idempotency = transition.idempotency
    new_version = transition.expected_version + 1
    profile_names = {
        "#pk": "PK",
        "#sk": "SK",
        "#version": "version",
        "#status": "status",
        "#gsi1pk": "GSI1PK",
        "#updatedAt": "updatedAt",
        "#updatedBy": "updatedBy",
    }
    profile_values = {
        ":expected": transition.expected_version,
        ":source": transition.source_status,
        ":target": transition.target_status,
        ":statusKey": f"STATUS#{transition.target_status}",
        ":version": new_version,
        ":updatedAt": audit_event.occurred_at,
        ":updatedBy": audit_event.actor_id,
    }
    sort_key = f"TS#{audit_event.occurred_at}#EVENT#{audit_event.event_id}"
    audit: dict[str, object] = {
        "PK": f"RESOURCE#STUDENT#{transition.student_id}",
        "SK": sort_key,
        "eventId": audit_event.event_id,
        "eventType": event_type,
        "resourceType": "STUDENT",
        "resourceId": transition.student_id,
        "actorId": audit_event.actor_id,
        "occurredAt": audit_event.occurred_at,
        "result": "SUCCESS",
        "correlationId": audit_event.correlation_id,
        "changes": {
            "status": {"from": transition.source_status, "to": transition.target_status},
            "version": {"from": transition.expected_version, "to": new_version},
        },
        "GSI1PK": f"ACTOR#{audit_event.actor_id}",
        "GSI1SK": sort_key,
        "GSI2PK": f"CORRELATION#{audit_event.correlation_id}",
        "GSI2SK": sort_key,
        "GSI3PK": f"PERIOD#{audit_event.occurred_at[:7]}",
        "GSI3SK": sort_key,
        "expiresAt": audit_event.audit_expires_at,
    }
    if audit_event.reason is not None:
        audit["reason"] = audit_event.reason

    return [
        {
            "Update": {
                "TableName": students_table,
                "Key": serialize({"PK": f"STUDENT#{transition.student_id}", "SK": "PROFILE"}),
                "UpdateExpression": (
                    "SET #status = :target, #gsi1pk = :statusKey, #version = :version, "
                    "#updatedAt = :updatedAt, #updatedBy = :updatedBy"
                ),
                "ConditionExpression": (
                    "attribute_exists(#pk) AND attribute_exists(#sk) "
                    "AND #version = :expected AND #status = :source"
                ),
                "ExpressionAttributeNames": profile_names,
                "ExpressionAttributeValues": serialize(profile_values),
            }
        },
        {
            "Put": {
                "TableName": audit_table,
                "Item": serialize(audit),
                "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
            }
        },
        {
            "Update": {
                "TableName": idempotency_table,
                "Key": serialize({"id": idempotency.idempotency_id}),
                "UpdateExpression": "SET #status = :completed, #data = :data",
                "ConditionExpression": (
                    "attribute_exists(#id) AND #status = :pending AND #validation = :hash"
                ),
                "ExpressionAttributeNames": {
                    "#id": "id",
                    "#status": "status",
                    "#data": "data",
                    "#validation": "validation",
                },
                "ExpressionAttributeValues": serialize(
                    {
                        ":completed": "COMPLETED",
                        ":pending": "INPROGRESS",
                        ":data": json.dumps(
                            transition.public_response, sort_keys=True, separators=(",", ":")
                        ),
                        ":hash": idempotency.request_hash,
                    }
                ),
            }
        },
    ]


def classify_lifecycle_failure(error: ClientError) -> None:
    """Classify only complete conditional evidence without guessing version or status."""
    reasons = error.response.get("CancellationReasons")
    if (
        error.response.get("Error", {}).get("Code") != "TransactionCanceledException"
        or not isinstance(reasons, list)
        or len(reasons) != 3
        or any(
            not isinstance(reason, dict)
            or reason.get("Code") not in {"None", "ConditionalCheckFailed"}
            for reason in reasons
        )
    ):
        raise StudentLifecycleUnresolvedError from error
    failed = {
        index for index, reason in enumerate(reasons) if reason["Code"] == "ConditionalCheckFailed"
    }
    if failed == {0}:
        raise StudentLifecycleConditionError from error
    if failed & {1, 2}:
        raise StudentLifecycleInvariantError from error
    raise StudentLifecycleUnresolvedError from error


def _validate_transition(
    transition: LifecycleTransition,
    *,
    students_table: str,
    audit_table: str,
    idempotency_table: str,
) -> str:
    audit_event = transition.audit_event
    idempotency = transition.idempotency
    pair = (transition.source_status, transition.target_status)
    event_type = {
        ("ACTIVE", "INACTIVE"): "STUDENT_DEACTIVATED",
        ("INACTIVE", "ACTIVE"): "STUDENT_REACTIVATED",
    }.get(pair)
    response = transition.public_response
    common_invalid = (
        event_type is None
        or not transition.student_id
        or type(transition.expected_version) is not int
        or transition.expected_version < 1
        or len({students_table, audit_table, idempotency_table}) != 3
        or set(response) != set(PUBLIC_FIELDS)
        or response.get("studentId") != transition.student_id
        or response.get("status") != transition.target_status
        or response.get("version") != transition.expected_version + 1
        or response.get("updatedAt") != audit_event.occurred_at
        or not all(
            isinstance(value, str)
            for value in (
                audit_event.actor_id,
                audit_event.correlation_id,
                audit_event.event_id,
                audit_event.occurred_at,
                idempotency.idempotency_id,
                idempotency.request_hash,
                idempotency.client_request_token,
            )
        )
        or not all(
            value
            for value in (
                audit_event.actor_id,
                audit_event.correlation_id,
                audit_event.event_id,
                audit_event.occurred_at,
                idempotency.idempotency_id,
                idempotency.request_hash,
            )
        )
        or not 1 <= len(idempotency.client_request_token) <= 36
    )
    reason_invalid = (
        pair == ("ACTIVE", "INACTIVE")
        and (
            not isinstance(audit_event.reason, str)
            or audit_event.reason != audit_event.reason.strip()
            or not 5 <= len(audit_event.reason) <= 300
        )
    ) or (pair == ("INACTIVE", "ACTIVE") and audit_event.reason is not None)
    if common_invalid or reason_invalid:
        raise StudentLifecycleInvariantError
    assert event_type is not None
    return event_type

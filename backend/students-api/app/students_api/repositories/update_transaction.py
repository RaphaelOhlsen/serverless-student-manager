"""Build one effective update transaction; no acquisition, replay or HTTP policy."""

import json
from dataclasses import dataclass
from typing import Any

from boto3.dynamodb.types import TypeSerializer  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from students_api.cursor import normalize_name
from students_api.errors import (
    StudentEmailAlreadyExistsError,
    StudentUpdateInvariantError,
    StudentUpdateUnresolvedError,
    StudentVersionConflictError,
)

PUBLIC_FIELDS = (
    "studentId",
    "registrationNumber",
    "fullName",
    "studentEmail",
    "phone",
    "birthDate",
    "status",
    "version",
    "createdAt",
    "updatedAt",
)
MUTABLE_FIELDS = ("fullName", "studentEmail", "phone", "birthDate")


@dataclass(frozen=True)
class UpdateTransactionContext:
    actor_id: str
    correlation_id: str
    event_id: str
    occurred_at: str
    audit_expires_at: int
    # Powertools persists this key after hashing environment/actor/operation/key.
    idempotency_id: str
    request_hash: str
    client_request_token: str


def serialize(item: dict[str, Any]) -> dict[str, Any]:
    serializer = TypeSerializer()
    return {key: serializer.serialize(value) for key, value in item.items()}


def build_update_transaction(
    *,
    current: dict[str, Any],
    target: dict[str, Any],
    expected_version: int,
    context: UpdateTransactionContext,
    students_table: str,
    audit_table: str,
    idempotency_table: str,
) -> tuple[list[dict[str, Any]], bool]:
    """Target contains the four resolved, normalized mutable fields only.

    The caller supplies an acquired update-student idempotency record using the
    Powertools id/status/validation/data schema. The id is already scoped by
    environment, actor, operation and key; validation is the normalized request
    hash. expiration is retained unchanged. Context must remain stable across retries.
    """
    if (
        set(target) != set(MUTABLE_FIELDS)
        or type(expected_version) is not int
        or expected_version < 1
        or current.get("version") != expected_version
        or len({students_table, audit_table, idempotency_table}) != 3
        or not 1 <= len(context.client_request_token) <= 36
    ):
        raise StudentUpdateInvariantError
    changed = [name for name in MUTABLE_FIELDS if current[name] != target[name]]
    if not changed:
        raise StudentUpdateInvariantError  # No-op belongs to the caller, never this transaction.
    student_id = current["studentId"]
    values = {name: target[name] for name in changed}
    values.update(
        version=expected_version + 1, updatedAt=context.occurred_at, updatedBy=context.actor_id
    )
    if "fullName" in changed:
        normalized = normalize_name(target["fullName"])
        name_key = f"NAME#{normalized}#STUDENT#{student_id}"
        values.update(normalizedName=normalized, GSI1SK=name_key, GSI2SK=name_key)
    names = {f"#f{i}": name for i, name in enumerate(values)}
    expressions = {f":v{i}": value for i, value in enumerate(values.values())}
    names.update({"#version": "version", "#pk": "PK", "#sk": "SK"})
    expressions[":expected"] = expected_version
    items = [
        {
            "Update": {
                "TableName": students_table,
                "Key": serialize({"PK": f"STUDENT#{student_id}", "SK": "PROFILE"}),
                "UpdateExpression": "SET "
                + ", ".join(f"#f{i} = :v{i}" for i in range(len(values))),
                "ConditionExpression": (
                    "attribute_exists(#pk) AND attribute_exists(#sk) AND #version = :expected"
                ),
                "ExpressionAttributeNames": names,
                "ExpressionAttributeValues": serialize(expressions),
            }
        }
    ]
    email_changed = "studentEmail" in changed
    if email_changed:
        items.extend(
            [
                {
                    "Put": {
                        "TableName": students_table,
                        "Item": serialize(
                            {
                                "PK": f"UNIQUE#EMAIL#{target['studentEmail']}",
                                "SK": "UNIQUE",
                                "studentId": student_id,
                            }
                        ),
                        "ConditionExpression": (
                            "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                        ),
                    }
                },
                {
                    "Delete": {
                        "TableName": students_table,
                        "Key": serialize(
                            {
                                "PK": f"UNIQUE#EMAIL#{current['studentEmail']}",
                                "SK": "UNIQUE",
                            }
                        ),
                        "ConditionExpression": (
                            "attribute_exists(PK) AND attribute_exists(SK) AND #owner = :owner"
                        ),
                        "ExpressionAttributeNames": {"#owner": "studentId"},
                        "ExpressionAttributeValues": serialize({":owner": student_id}),
                    }
                },
            ]
        )
    sort_key = f"TS#{context.occurred_at}#EVENT#{context.event_id}"
    audit = {
        "PK": f"RESOURCE#STUDENT#{student_id}",
        "SK": sort_key,
        "eventId": context.event_id,
        "eventType": "STUDENT_UPDATED",
        "resourceType": "STUDENT",
        "resourceId": student_id,
        "actorId": context.actor_id,
        "occurredAt": context.occurred_at,
        "result": "SUCCESS",
        "correlationId": context.correlation_id,
        "changes": {
            "fields": changed,
            "version": {"from": expected_version, "to": expected_version + 1},
        },
        "GSI1PK": f"ACTOR#{context.actor_id}",
        "GSI1SK": sort_key,
        "GSI2PK": f"CORRELATION#{context.correlation_id}",
        "GSI2SK": sort_key,
        "GSI3PK": f"PERIOD#{context.occurred_at[:7]}",
        "GSI3SK": sort_key,
        "expiresAt": context.audit_expires_at,
    }
    response = {name: current[name] for name in PUBLIC_FIELDS}
    response.update(target)
    response.update(version=expected_version + 1, updatedAt=context.occurred_at)
    items.extend(
        [
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
                    "Key": serialize({"id": context.idempotency_id}),
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
                            ":data": json.dumps(response, sort_keys=True, separators=(",", ":")),
                            ":hash": context.request_hash,
                        }
                    ),
                }
            },
        ]
    )
    return items, email_changed


def classify_update_failure(error: ClientError, *, email_changed: bool) -> None:
    """Only complete, purely conditional cancellation evidence is classifiable."""
    reasons = error.response.get("CancellationReasons")
    count = 5 if email_changed else 3
    if (
        error.response.get("Error", {}).get("Code") != "TransactionCanceledException"
        or not isinstance(reasons, list)
        or len(reasons) != count
        or any(
            not isinstance(r, dict) or r.get("Code") not in {"None", "ConditionalCheckFailed"}
            for r in reasons
        )
    ):
        raise StudentUpdateUnresolvedError from error
    failed = {i for i, reason in enumerate(reasons) if reason["Code"] == "ConditionalCheckFailed"}
    functional = {0, 1} if email_changed else {0}
    if failed - functional:
        raise StudentUpdateInvariantError from error
    if 0 in failed:
        raise StudentVersionConflictError from error
    if email_changed and 1 in failed:
        raise StudentEmailAlreadyExistsError from error
    raise StudentUpdateUnresolvedError from error

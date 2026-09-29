from collections.abc import Mapping

from audit_api.errors import AuditEventDataInvariantError, InvalidAuditQueryRequestError
from audit_api.query import normalize_rfc3339_utc, valid_exact_value

_PUBLIC_FIELDS = (
    "eventId",
    "eventType",
    "resourceType",
    "resourceId",
    "actorId",
    "occurredAt",
    "result",
    "correlationId",
)


def serialize_public_event(item: Mapping[str, object]) -> dict[str, str]:
    values: dict[str, str] = {}
    for field in _PUBLIC_FIELDS:
        value = item.get(field)
        if not valid_exact_value(value):
            raise AuditEventDataInvariantError
        values[field] = value

    if values["resourceType"] not in {"STUDENT", "USER"}:
        raise AuditEventDataInvariantError
    if values["result"] not in {"SUCCESS", "FAILURE"}:
        raise AuditEventDataInvariantError
    try:
        occurred_at, _ = normalize_rfc3339_utc(values["occurredAt"])
    except InvalidAuditQueryRequestError:
        raise AuditEventDataInvariantError from None
    values["occurredAt"] = occurred_at
    return values

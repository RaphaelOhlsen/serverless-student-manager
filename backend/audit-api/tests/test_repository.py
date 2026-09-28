from typing import Any

import pytest
from audit_api.cursor import EventPosition
from audit_api.errors import AuditEventDataInvariantError, InvalidAuditCursorError
from audit_api.query import AccessPath, AuditQuery, parse_audit_query
from audit_api.repository import AuditEventRepository


def query(**parameters: str) -> AuditQuery:
    values = {
        "from": "2026-08-01T00%3A00%3A00Z",
        "to": "2026-09-30T23%3A59%3A59.999Z",
        **parameters,
    }
    return parse_audit_query(
        {"rawQueryString": "&".join(f"{name}={value}" for name, value in values.items())}
    )


def event(
    *,
    event_id: str = "event-2",
    occurred_at: str = "2026-09-20T10:00:00.000Z",
    resource_type: str = "STUDENT",
    resource_id: str = "student-1",
    actor_id: str = "admin-1",
    correlation_id: str = "correlation-1",
) -> dict[str, object]:
    sort_key = f"TS#{occurred_at}#EVENT#{event_id}"
    return {
        "PK": f"RESOURCE#{resource_type}#{resource_id}",
        "SK": sort_key,
        "GSI1PK": f"ACTOR#{actor_id}",
        "GSI1SK": sort_key,
        "GSI2PK": f"CORRELATION#{correlation_id}",
        "GSI2SK": sort_key,
        "GSI3PK": f"PERIOD#{occurred_at[:7]}",
        "GSI3SK": sort_key,
        "eventId": event_id,
        "eventType": "STUDENT_UPDATED",
        "resourceType": resource_type,
        "resourceId": resource_id,
        "actorId": actor_id,
        "occurredAt": occurred_at,
        "result": "SUCCESS",
        "correlationId": correlation_id,
    }


class RecordingTable:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def query(self, **kwargs: Any) -> dict[str, object]:
        self.calls.append(kwargs)
        return self.response


@pytest.mark.parametrize(
    ("audit_query", "index_name", "partition_name", "partition_value", "sort_name"),
    [
        (
            query(resourceType="STUDENT", resourceId="student-1"),
            None,
            "PK",
            "RESOURCE#STUDENT#student-1",
            "SK",
        ),
        (query(actorId="admin-1"), "gsi-actor-time", "GSI1PK", "ACTOR#admin-1", "GSI1SK"),
        (
            query(correlationId="correlation-1"),
            "gsi-correlation-time",
            "GSI2PK",
            "CORRELATION#correlation-1",
            "GSI2SK",
        ),
        (query(), "gsi-period-time", "GSI3PK", "PERIOD#2026-09", "GSI3SK"),
    ],
)
def test_repository_uses_exact_access_path_and_descending_range(
    audit_query: AuditQuery,
    index_name: str | None,
    partition_name: str,
    partition_value: str,
    sort_name: str,
) -> None:
    item = event()
    table = RecordingTable({"Items": [item]})

    page = AuditEventRepository(table).query_page(
        audit_query,
        bucket="2026-09" if audit_query.access_path is AccessPath.PERIOD else None,
        position=None,
        limit=10,
    )

    assert page.items == [item]
    assert page.next_position is None
    call = table.calls[0]
    assert call["ScanIndexForward"] is False
    assert call["Limit"] == 10
    assert call["ExpressionAttributeNames"] == {"#pk": partition_name, "#sk": sort_name}
    assert call["ExpressionAttributeValues"] == {
        ":pk": partition_value,
        ":from": "TS#2026-08-01T00:00:00.000Z#EVENT#",
        ":to": "TS#2026-09-30T23:59:59.999Z#EVENT#\U0010ffff",
    }
    assert call["KeyConditionExpression"] == "#pk = :pk AND #sk BETWEEN :from AND :to"
    if index_name is None:
        assert "IndexName" not in call
    else:
        assert call["IndexName"] == index_name
    assert "FilterExpression" not in call


def test_repository_reconstructs_exclusive_start_key_from_logical_position() -> None:
    item = event()
    position = EventPosition(
        occurred_at="2026-09-20T10:00:00.000Z",
        event_id="event-2",
        resource_type="STUDENT",
        resource_id="student-1",
    )
    table = RecordingTable({"Items": [item]})

    AuditEventRepository(table).query_page(
        query(actorId="admin-1"), bucket=None, position=position, limit=4
    )

    assert table.calls[0]["ExclusiveStartKey"] == {
        "PK": "RESOURCE#STUDENT#student-1",
        "SK": "TS#2026-09-20T10:00:00.000Z#EVENT#event-2",
        "GSI1PK": "ACTOR#admin-1",
        "GSI1SK": "TS#2026-09-20T10:00:00.000Z#EVENT#event-2",
    }


def test_repository_converts_last_evaluated_key_to_logical_position() -> None:
    item = event()
    table = RecordingTable(
        {
            "Items": [item],
            "LastEvaluatedKey": {
                "PK": item["PK"],
                "SK": item["SK"],
                "GSI3PK": item["GSI3PK"],
                "GSI3SK": item["GSI3SK"],
            },
        }
    )

    page = AuditEventRepository(table).query_page(query(), bucket="2026-09", position=None, limit=1)

    assert page.next_position == EventPosition(
        occurred_at="2026-09-20T10:00:00.000Z",
        event_id="event-2",
        resource_type="STUDENT",
        resource_id="student-1",
    )


def test_repository_rejects_malformed_item_keys() -> None:
    item = event()
    item["SK"] = "wrong"

    with pytest.raises(AuditEventDataInvariantError):
        AuditEventRepository(RecordingTable({"Items": [item]})).query_page(
            query(), bucket="2026-09", position=None, limit=10
        )


def test_repository_rejects_impossible_position() -> None:
    position = EventPosition(
        occurred_at="2026-08-20T10:00:00.000Z",
        event_id="event-2",
        resource_type="STUDENT",
        resource_id="student-1",
    )

    with pytest.raises(InvalidAuditCursorError):
        AuditEventRepository(RecordingTable({"Items": []})).query_page(
            query(), bucket="2026-09", position=position, limit=10
        )

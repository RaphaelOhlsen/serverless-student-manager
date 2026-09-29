from dataclasses import replace
from typing import Any

import pytest
from audit_api.cursor import decode_cursor
from audit_api.errors import AuditEventDataInvariantError
from audit_api.query import AuditQuery, parse_audit_query
from audit_api.query_engine import AuditQueryEngine
from audit_api.repository import AuditEventRepository


def audit_query(**parameters: str) -> AuditQuery:
    values = {
        "from": "2026-08-01T00%3A00%3A00Z",
        "to": "2026-09-30T23%3A59%3A59.999Z",
        "limit": "2",
        **parameters,
    }
    return parse_audit_query(
        {"rawQueryString": "&".join(f"{name}={value}" for name, value in values.items())}
    )


def item(
    event_id: str,
    occurred_at: str,
    *,
    event_type: str = "STUDENT_UPDATED",
    resource_type: str = "STUDENT",
    resource_id: str = "student-1",
    actor_id: str = "admin-1",
    result: str = "SUCCESS",
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
        "eventType": event_type,
        "resourceType": resource_type,
        "resourceId": resource_id,
        "actorId": actor_id,
        "occurredAt": occurred_at,
        "result": result,
        "correlationId": correlation_id,
        "changes": {"private": True},
    }


class MemoryAuditTable:
    def __init__(self, items: list[dict[str, object]]) -> None:
        self.items = items
        self.calls: list[dict[str, Any]] = []

    def query(self, **kwargs: Any) -> dict[str, object]:
        self.calls.append(kwargs)
        names = kwargs["ExpressionAttributeNames"]
        values = kwargs["ExpressionAttributeValues"]
        pk_name = names["#pk"]
        sk_name = names["#sk"]
        matching = [
            candidate
            for candidate in self.items
            if candidate.get(pk_name) == values[":pk"]
            and values[":from"] <= candidate.get(sk_name, "") <= values[":to"]
        ]
        matching.sort(key=lambda candidate: str(candidate[sk_name]), reverse=True)
        exclusive_start_key = kwargs.get("ExclusiveStartKey")
        if exclusive_start_key is not None:
            for index, candidate in enumerate(matching):
                if all(candidate.get(name) == value for name, value in exclusive_start_key.items()):
                    matching = matching[index + 1 :]
                    break
            else:
                raise AssertionError("exclusive start key not found")

        limit = kwargs["Limit"]
        selected = matching[:limit]
        response: dict[str, object] = {"Items": selected}
        if len(matching) > limit:
            last = selected[-1]
            key_names = ["PK", "SK"]
            if "IndexName" in kwargs:
                key_names.extend([pk_name, sk_name])
            response["LastEvaluatedKey"] = {name: last[name] for name in key_names}
        return response

    def scan(self, **kwargs: Any) -> None:
        raise AssertionError("Scan must never be called")

    def get_item(self, **kwargs: Any) -> None:
        raise AssertionError("audit hydration must never be called")


def engine(
    items: list[dict[str, object]], *, max_query_calls: int = 20
) -> tuple[AuditQueryEngine, MemoryAuditTable]:
    table = MemoryAuditTable(items)
    return AuditQueryEngine(AuditEventRepository(table), max_query_calls=max_query_calls), table


def test_post_filters_and_fills_page_across_multiple_queries() -> None:
    events = [
        item("event-5", "2026-09-25T00:00:00.000Z", result="FAILURE"),
        item("event-4", "2026-09-24T00:00:00.000Z", event_type="STUDENT_CREATED"),
        item("event-3", "2026-09-23T00:00:00.000Z"),
        item("event-2", "2026-09-22T00:00:00.000Z", result="FAILURE"),
        item("event-1", "2026-09-21T00:00:00.000Z"),
    ]
    service, table = engine(events)

    page = service.execute(
        audit_query(
            resourceType="STUDENT",
            resourceId="student-1",
            eventType="STUDENT_UPDATED",
            result="SUCCESS",
        )
    )

    assert [entry["eventId"] for entry in page.items] == ["event-3", "event-1"]
    assert len(table.calls) == 3
    assert page.next_cursor is None
    assert all("FilterExpression" not in call for call in table.calls)


def test_single_partition_cursor_has_no_duplicates_or_omissions() -> None:
    events = [
        item(f"event-{number}", f"2026-09-2{number}T00:00:00.000Z") for number in range(5, 0, -1)
    ]
    service, _ = engine(events)
    query = audit_query(actorId="admin-1")

    first = service.execute(query)
    second = service.execute(replace(query, cursor=first.next_cursor))
    third = service.execute(replace(query, cursor=second.next_cursor))

    assert [entry["eventId"] for entry in first.items + second.items + third.items] == [
        "event-5",
        "event-4",
        "event-3",
        "event-2",
        "event-1",
    ]
    assert first.next_cursor is not None
    assert second.next_cursor is not None
    assert third.next_cursor is None


def test_same_timestamp_is_ordered_by_event_id_descending() -> None:
    events = [
        item("event-a", "2026-09-20T00:00:00.000Z"),
        item("event-c", "2026-09-20T00:00:00.000Z"),
        item("event-b", "2026-09-20T00:00:00.000Z"),
    ]
    service, _ = engine(events)

    first = service.execute(audit_query(correlationId="correlation-1"))
    second = service.execute(
        replace(audit_query(correlationId="correlation-1"), cursor=first.next_cursor)
    )

    assert [entry["eventId"] for entry in first.items + second.items] == [
        "event-c",
        "event-b",
        "event-a",
    ]


def test_period_page_crosses_month_boundary_and_continues_without_gaps() -> None:
    events = [
        item("sep-2", "2026-09-02T00:00:00.000Z"),
        item("aug-2", "2026-08-31T23:00:00.000Z"),
        item("aug-1", "2026-08-01T00:00:00.000Z"),
    ]
    service, table = engine(events)
    query = audit_query()

    first = service.execute(query)
    continuation = decode_cursor(first.next_cursor or "", query)
    second = service.execute(replace(query, cursor=first.next_cursor))

    assert [entry["eventId"] for entry in first.items] == ["sep-2", "aug-2"]
    assert continuation.bucket == "2026-08"
    assert continuation.position is not None
    assert [entry["eventId"] for entry in second.items] == ["aug-1"]
    assert second.next_cursor is None
    assert [call["ExpressionAttributeValues"][":pk"] for call in table.calls] == [
        "PERIOD#2026-09",
        "PERIOD#2026-08",
        "PERIOD#2026-08",
    ]


def test_period_cursor_can_continue_after_exhausted_month_transition() -> None:
    events = [item("aug-1", "2026-08-20T00:00:00.000Z")]
    service, _ = engine(events, max_query_calls=1)
    query = audit_query()

    first = service.execute(query)
    continuation = decode_cursor(first.next_cursor or "", query)
    second = service.execute(replace(query, cursor=first.next_cursor))

    assert first.items == []
    assert continuation.bucket == "2026-08"
    assert continuation.position is None
    assert [entry["eventId"] for entry in second.items] == ["aug-1"]


def test_sparse_filter_work_bound_returns_progressing_cursor() -> None:
    events = [
        item(f"event-{number}", f"2026-09-{number:02d}T00:00:00.000Z", result="FAILURE")
        for number in range(10, 0, -1)
    ]
    service, _ = engine(events, max_query_calls=2)
    query = audit_query(resourceType="STUDENT", resourceId="student-1", result="SUCCESS")

    first = service.execute(query)
    second = service.execute(replace(query, cursor=first.next_cursor))

    assert first.items == []
    assert second.items == []
    assert first.next_cursor is not None
    assert second.next_cursor is not None
    assert first.next_cursor != second.next_cursor


def test_empty_exhausted_result_has_null_cursor() -> None:
    service, table = engine([])

    page = service.execute(audit_query(resourceType="USER"))

    assert page.items == []
    assert page.next_cursor is None
    assert len(table.calls) == 2


def test_period_access_path_post_filters_resource_type() -> None:
    events = [
        item("student-event", "2026-09-20T00:00:00.000Z"),
        item(
            "user-event",
            "2026-09-19T00:00:00.000Z",
            resource_type="USER",
            resource_id="user-1",
        ),
    ]
    service, _ = engine(events)

    page = service.execute(audit_query(resourceType="USER"))

    assert [entry["eventId"] for entry in page.items] == ["user-event"]
    assert page.next_cursor is None


def test_malformed_summary_fails_closed() -> None:
    malformed = item("event-1", "2026-09-20T00:00:00.000Z")
    malformed["result"] = "DENIED"
    service, _ = engine([malformed])

    with pytest.raises(AuditEventDataInvariantError):
        service.execute(audit_query())


def test_cursor_payload_contains_no_physical_key_names() -> None:
    events = [
        item("event-2", "2026-09-20T00:00:00.000Z"),
        item("event-1", "2026-09-19T00:00:00.000Z"),
    ]
    service, _ = engine(events, max_query_calls=1)

    cursor = service.execute(audit_query(limit="1")).next_cursor
    assert cursor is not None
    decoded = __import__("base64").urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
    assert all(name not in decoded for name in ("PK", "SK", "GSI1", "GSI2", "GSI3"))

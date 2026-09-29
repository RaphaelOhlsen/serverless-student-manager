from urllib.parse import urlencode

import pytest
from audit_api.errors import InvalidAuditQueryRequestError
from audit_api.query import AccessPath, parse_audit_query, select_access_path


def event(*pairs: tuple[str, str]) -> dict[str, str]:
    return {"rawQueryString": urlencode(pairs)}


def test_parses_and_normalizes_complete_query() -> None:
    query = parse_audit_query(
        event(
            ("from", "2026-09-01T00:00:00Z"),
            ("to", "2026-09-28T14:30:00.120Z"),
            ("resourceType", "STUDENT"),
            ("resourceId", "student-1"),
            ("eventType", "STUDENT_UPDATED"),
            ("actorId", "admin-1"),
            ("result", "SUCCESS"),
            ("correlationId", "correlation-1"),
            ("limit", "100"),
        )
    )

    assert query.from_timestamp == "2026-09-01T00:00:00.000Z"
    assert query.to_timestamp == "2026-09-28T14:30:00.120Z"
    assert query.limit == 100
    assert query.access_path is AccessPath.CORRELATION


def test_defaults_limit_and_period_access_path() -> None:
    query = parse_audit_query(
        event(("from", "2026-09-01T00:00:00Z"), ("to", "2026-09-02T00:00:00Z"))
    )

    assert query.limit == 50
    assert query.access_path is AccessPath.PERIOD


@pytest.mark.parametrize(
    "pairs",
    [
        (("to", "2026-09-02T00:00:00Z"),),
        (("from", "2026-09-01T00:00:00Z"),),
        (
            ("from", "2026-09-01T00:00:00+00:00"),
            ("to", "2026-09-02T00:00:00Z"),
        ),
        (
            ("from", "2026-09-01T00:00:00.123456Z"),
            ("to", "2026-09-02T00:00:00Z"),
        ),
        (
            ("from", "2026-09-02T00:00:00Z"),
            ("to", "2026-09-01T00:00:00Z"),
        ),
        (
            ("from", "2025-01-01T00:00:00Z"),
            ("to", "2026-01-03T00:00:00Z"),
        ),
        (
            ("from", "2026-09-01T00:00:00Z"),
            ("to", "2026-09-02T00:00:00Z"),
            ("resourceType", "COURSE"),
        ),
        (
            ("from", "2026-09-01T00:00:00Z"),
            ("to", "2026-09-02T00:00:00Z"),
            ("resourceId", "student-1"),
        ),
        (
            ("from", "2026-09-01T00:00:00Z"),
            ("to", "2026-09-02T00:00:00Z"),
            ("result", "DENIED"),
        ),
        (
            ("from", "2026-09-01T00:00:00Z"),
            ("to", "2026-09-02T00:00:00Z"),
            ("limit", "0"),
        ),
        (
            ("from", "2026-09-01T00:00:00Z"),
            ("to", "2026-09-02T00:00:00Z"),
            ("limit", "101"),
        ),
        (
            ("from", "2026-09-01T00:00:00Z"),
            ("to", "2026-09-02T00:00:00Z"),
            ("unknown", "value"),
        ),
        (
            ("from", "2026-09-01T00:00:00Z"),
            ("to", "2026-09-02T00:00:00Z"),
            ("eventType", ""),
        ),
        (
            ("from", "2026-09-01T00:00:00Z"),
            ("to", "2026-09-02T00:00:00Z"),
            ("actorId", " admin "),
        ),
    ],
)
def test_rejects_invalid_queries(pairs: tuple[tuple[str, str], ...]) -> None:
    with pytest.raises(InvalidAuditQueryRequestError):
        parse_audit_query(event(*pairs))


def test_rejects_repeated_parameter_from_raw_query_string() -> None:
    raw_event = {
        "rawQueryString": (
            "from=2026-09-01T00%3A00%3A00Z&to=2026-09-02T00%3A00%3A00Z&limit=10&limit=20"
        ),
        "queryStringParameters": {
            "from": "2026-09-01T00:00:00Z",
            "to": "2026-09-02T00:00:00Z",
            "limit": "20",
        },
    }

    with pytest.raises(InvalidAuditQueryRequestError):
        parse_audit_query(raw_event)


@pytest.mark.parametrize("malformed", ["%", "%GG", "%FF"])
def test_rejects_malformed_percent_encoding(malformed: str) -> None:
    raw_event = {
        "rawQueryString": (
            f"from=2026-09-01T00%3A00%3A00Z&to=2026-09-02T00%3A00%3A00Z&actorId={malformed}"
        )
    }

    with pytest.raises(InvalidAuditQueryRequestError):
        parse_audit_query(raw_event)


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (
            {
                "correlation_id": "c",
                "resource_type": "STUDENT",
                "resource_id": "r",
                "actor_id": "a",
            },
            AccessPath.CORRELATION,
        ),
        ({"resource_type": "STUDENT", "resource_id": "r", "actor_id": "a"}, AccessPath.RESOURCE),
        ({"actor_id": "a"}, AccessPath.ACTOR),
        ({"resource_type": "STUDENT"}, AccessPath.PERIOD),
        ({}, AccessPath.PERIOD),
    ],
)
def test_access_path_priority(filters: dict[str, str], expected: AccessPath) -> None:
    assert select_access_path(**filters) is expected

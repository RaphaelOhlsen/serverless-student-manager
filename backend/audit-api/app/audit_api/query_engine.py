from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from audit_api.cursor import CursorContinuation, EventPosition, decode_cursor, encode_cursor
from audit_api.query import AccessPath, AuditQuery
from audit_api.repository import RepositoryPage
from audit_api.serializer import serialize_public_event

DEFAULT_MAX_QUERY_CALLS = 20


class AuditRepositoryProtocol(Protocol):
    def query_page(
        self,
        query: AuditQuery,
        *,
        bucket: str | None,
        position: EventPosition | None,
        limit: int,
    ) -> RepositoryPage: ...


@dataclass(frozen=True)
class AuditPage:
    items: list[dict[str, str]]
    next_cursor: str | None


class AuditQueryEngine:
    def __init__(
        self,
        repository: AuditRepositoryProtocol,
        *,
        max_query_calls: int = DEFAULT_MAX_QUERY_CALLS,
    ) -> None:
        if max_query_calls < 1:
            raise ValueError("max_query_calls must be positive")
        self._repository = repository
        self._max_query_calls = max_query_calls

    def execute(self, query: AuditQuery) -> AuditPage:
        buckets = _covered_months(query)
        continuation = self._initial_continuation(query, buckets)
        items: list[dict[str, str]] = []
        calls = 0
        exhausted = False

        while len(items) < query.limit and calls < self._max_query_calls:
            repository_page = self._repository.query_page(
                query,
                bucket=continuation.bucket,
                position=continuation.position,
                limit=query.limit - len(items),
            )
            calls += 1
            public_items = [serialize_public_event(item) for item in repository_page.items]
            items.extend(item for item in public_items if _matches_filters(item, query))

            if repository_page.next_position is not None:
                continuation = CursorContinuation(
                    bucket=continuation.bucket,
                    position=repository_page.next_position,
                )
            elif query.access_path is AccessPath.PERIOD:
                next_bucket = _next_bucket(continuation.bucket, buckets)
                if next_bucket is None:
                    exhausted = True
                else:
                    continuation = CursorContinuation(bucket=next_bucket, position=None)
            else:
                exhausted = True

            if exhausted:
                break

        next_cursor = None if exhausted else encode_cursor(query, continuation)
        return AuditPage(items=items, next_cursor=next_cursor)

    @staticmethod
    def _initial_continuation(query: AuditQuery, buckets: tuple[str, ...]) -> CursorContinuation:
        if query.cursor is not None:
            return decode_cursor(query.cursor, query)
        if query.access_path is AccessPath.PERIOD:
            return CursorContinuation(bucket=buckets[0], position=None)
        return CursorContinuation(bucket=None, position=None)


def _matches_filters(item: dict[str, str], query: AuditQuery) -> bool:
    expected = {
        "resourceType": query.resource_type,
        "resourceId": query.resource_id,
        "eventType": query.event_type,
        "actorId": query.actor_id,
        "result": query.result,
        "correlationId": query.correlation_id,
    }
    return all(value is None or item[name] == value for name, value in expected.items())


def _covered_months(query: AuditQuery) -> tuple[str, ...]:
    current = datetime.strptime(query.to_timestamp[:7], "%Y-%m")
    oldest = datetime.strptime(query.from_timestamp[:7], "%Y-%m")
    months: list[str] = []
    while current >= oldest:
        months.append(current.strftime("%Y-%m"))
        if current.month == 1:
            current = current.replace(year=current.year - 1, month=12)
        else:
            current = current.replace(month=current.month - 1)
    return tuple(months)


def _next_bucket(current: str | None, buckets: tuple[str, ...]) -> str | None:
    if current is None:
        raise RuntimeError("Period continuation lacks its bucket")
    try:
        index = buckets.index(current)
    except ValueError:
        raise RuntimeError("Period continuation bucket is outside the query") from None
    return buckets[index + 1] if index + 1 < len(buckets) else None

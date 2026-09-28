from dataclasses import dataclass
from typing import Any, Protocol

from audit_api.cursor import CursorContinuation, EventPosition, validate_continuation
from audit_api.errors import AuditEventDataInvariantError, InvalidAuditCursorError
from audit_api.query import AccessPath, AuditQuery
from audit_api.serializer import serialize_public_event

_INDEXES: dict[AccessPath, tuple[str | None, str, str]] = {
    AccessPath.RESOURCE: (None, "PK", "SK"),
    AccessPath.ACTOR: ("gsi-actor-time", "GSI1PK", "GSI1SK"),
    AccessPath.CORRELATION: ("gsi-correlation-time", "GSI2PK", "GSI2SK"),
    AccessPath.PERIOD: ("gsi-period-time", "GSI3PK", "GSI3SK"),
}


class AuditTableProtocol(Protocol):
    def query(self, **kwargs: Any) -> dict[str, object]: ...


@dataclass(frozen=True)
class RepositoryPage:
    items: list[dict[str, object]]
    next_position: EventPosition | None


class AuditEventRepository:
    def __init__(self, table: AuditTableProtocol) -> None:
        self._table = table

    def query_page(
        self,
        query: AuditQuery,
        *,
        bucket: str | None,
        position: EventPosition | None,
        limit: int,
    ) -> RepositoryPage:
        self._validate_state(query, bucket, position)
        if not 1 <= limit <= query.limit:
            raise ValueError("Repository query limit is outside the public page bound")

        index_name, partition_name, sort_name = _INDEXES[query.access_path]
        partition_value = self._partition_value(query, bucket)
        request: dict[str, Any] = {
            "KeyConditionExpression": "#pk = :pk AND #sk BETWEEN :from AND :to",
            "ExpressionAttributeNames": {"#pk": partition_name, "#sk": sort_name},
            "ExpressionAttributeValues": {
                ":pk": partition_value,
                ":from": f"TS#{query.from_timestamp}#EVENT#",
                ":to": f"TS#{query.to_timestamp}#EVENT#\U0010ffff",
            },
            "Limit": limit,
            "ScanIndexForward": False,
        }
        if index_name is not None:
            request["IndexName"] = index_name
        if position is not None:
            request["ExclusiveStartKey"] = self._exclusive_start_key(query, bucket, position)

        response = self._table.query(**request)
        raw_items = response.get("Items")
        if not isinstance(raw_items, list) or not all(isinstance(item, dict) for item in raw_items):
            raise AuditEventDataInvariantError
        items = list(raw_items)
        for item in items:
            self._validate_item(item, query, bucket)

        last_key = response.get("LastEvaluatedKey")
        next_position = self._position_from_last_key(last_key, query, bucket)
        if next_position is not None and items:
            public_last = serialize_public_event(items[-1])
            if next_position != _event_position(public_last):
                raise AuditEventDataInvariantError
        return RepositoryPage(items=items, next_position=next_position)

    @staticmethod
    def _validate_state(
        query: AuditQuery, bucket: str | None, position: EventPosition | None
    ) -> None:
        if query.access_path is AccessPath.PERIOD:
            continuation = CursorContinuation(bucket, position)
        elif position is not None:
            continuation = CursorContinuation(None, position)
        else:
            return
        validate_continuation(query, continuation)

    @staticmethod
    def _partition_value(query: AuditQuery, bucket: str | None) -> str:
        if query.access_path is AccessPath.RESOURCE:
            if query.resource_type is None or query.resource_id is None:
                raise RuntimeError("Resource access path lacks its partition values")
            return f"RESOURCE#{query.resource_type}#{query.resource_id}"
        if query.access_path is AccessPath.ACTOR:
            if query.actor_id is None:
                raise RuntimeError("Actor access path lacks its partition value")
            return f"ACTOR#{query.actor_id}"
        if query.access_path is AccessPath.CORRELATION:
            if query.correlation_id is None:
                raise RuntimeError("Correlation access path lacks its partition value")
            return f"CORRELATION#{query.correlation_id}"
        if bucket is None:
            raise InvalidAuditCursorError
        return f"PERIOD#{bucket}"

    def _exclusive_start_key(
        self, query: AuditQuery, bucket: str | None, position: EventPosition
    ) -> dict[str, str]:
        sort_key = f"TS#{position.occurred_at}#EVENT#{position.event_id}"
        key = {
            "PK": f"RESOURCE#{position.resource_type}#{position.resource_id}",
            "SK": sort_key,
        }
        _, partition_name, sort_name = _INDEXES[query.access_path]
        if query.access_path is not AccessPath.RESOURCE:
            key[partition_name] = self._partition_value(query, bucket)
            key[sort_name] = sort_key
        return key

    def _position_from_last_key(
        self, value: object, query: AuditQuery, bucket: str | None
    ) -> EventPosition | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise AuditEventDataInvariantError
        _, partition_name, sort_name = _INDEXES[query.access_path]
        expected = {"PK", "SK"}
        if query.access_path is not AccessPath.RESOURCE:
            expected.update({partition_name, sort_name})
        if set(value) != expected or not all(isinstance(item, str) for item in value.values()):
            raise AuditEventDataInvariantError
        if query.access_path is not AccessPath.RESOURCE and (
            value[partition_name] != self._partition_value(query, bucket)
            or value[sort_name] != value["SK"]
        ):
            raise AuditEventDataInvariantError
        position = _parse_physical_position(value["PK"], value["SK"])
        self._validate_state(query, bucket, position)
        return position

    def _validate_item(
        self, item: dict[str, object], query: AuditQuery, bucket: str | None
    ) -> None:
        public = serialize_public_event(item)
        position = _event_position(public)
        expected_sort = f"TS#{position.occurred_at}#EVENT#{position.event_id}"
        if (
            item.get("PK") != f"RESOURCE#{position.resource_type}#{position.resource_id}"
            or item.get("SK") != expected_sort
        ):
            raise AuditEventDataInvariantError
        _, partition_name, sort_name = _INDEXES[query.access_path]
        if query.access_path is not AccessPath.RESOURCE and (
            item.get(partition_name) != self._partition_value(query, bucket)
            or item.get(sort_name) != expected_sort
        ):
            raise AuditEventDataInvariantError


def _parse_physical_position(partition_key: object, sort_key: object) -> EventPosition:
    if not isinstance(partition_key, str) or not isinstance(sort_key, str):
        raise AuditEventDataInvariantError
    partition_parts = partition_key.split("#", 2)
    if len(partition_parts) != 3 or partition_parts[0] != "RESOURCE":
        raise AuditEventDataInvariantError
    if not sort_key.startswith("TS#") or "#EVENT#" not in sort_key:
        raise AuditEventDataInvariantError
    occurred_at, event_id = sort_key.removeprefix("TS#").split("#EVENT#", 1)
    return EventPosition(occurred_at, event_id, partition_parts[1], partition_parts[2])


def _event_position(public: dict[str, str]) -> EventPosition:
    return EventPosition(
        occurred_at=public["occurredAt"],
        event_id=public["eventId"],
        resource_type=public["resourceType"],
        resource_id=public["resourceId"],
    )

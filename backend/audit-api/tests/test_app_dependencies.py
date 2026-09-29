import json
from typing import cast

import pytest
from audit_api import config, dependencies
from audit_api.query_engine import AuditPage
from aws_lambda_powertools.utilities.typing import LambdaContext
from test_routes import FakeContext, FakeService, event


def test_functional_route_is_registered_in_production_app(monkeypatch: pytest.MonkeyPatch) -> None:
    from audit_api import app as app_module

    service = FakeService(AuditPage(items=[], next_cursor=None))
    monkeypatch.setattr("audit_api.routes.audit_events.get_audit_query_service", lambda: service)

    response = app_module.app.resolve(event(), cast(LambdaContext, FakeContext()))

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"items": [], "nextCursor": None}
    assert len(service.calls) == 1


def test_lambda_handler_resolves_registered_route(monkeypatch: pytest.MonkeyPatch) -> None:
    from audit_api import app as app_module

    service = FakeService(AuditPage(items=[], next_cursor=None))
    monkeypatch.setattr("audit_api.routes.audit_events.get_audit_query_service", lambda: service)

    response = app_module.lambda_handler(event(), cast(LambdaContext, FakeContext()))

    assert response["statusCode"] == 200


def test_config_requires_table_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("USERS_TABLE_NAME", raising=False)
    monkeypatch.delenv("AUDIT_TABLE_NAME", raising=False)

    with pytest.raises(RuntimeError, match="USERS_TABLE_NAME"):
        config.get_users_table_name()
    with pytest.raises(RuntimeError, match="AUDIT_TABLE_NAME"):
        config.get_audit_table_name()


class FakeDynamoDB:
    def __init__(self) -> None:
        self.names: list[str] = []

    def Table(self, name: str) -> object:
        self.names.append(name)
        return object()


def test_dependency_wiring_uses_only_users_and_audit_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dynamodb = FakeDynamoDB()
    monkeypatch.setenv("USERS_TABLE_NAME", "users-table")
    monkeypatch.setenv("AUDIT_TABLE_NAME", "audit-table")
    monkeypatch.setattr("audit_api.dependencies.boto3.resource", lambda service: dynamodb)
    dependencies.get_audit_query_service.cache_clear()

    service = dependencies.get_audit_query_service()

    assert service is not None
    assert dynamodb.names == ["users-table", "audit-table"]
    dependencies.get_audit_query_service.cache_clear()


def test_runtime_requirements_are_pinned() -> None:
    from pathlib import Path

    requirements = (Path(__file__).resolve().parents[1] / "app" / "requirements.txt").read_text(
        encoding="utf-8"
    )

    assert "aws-lambda-powertools==3.34.0" in requirements
    assert "boto3==1.43.70" in requirements

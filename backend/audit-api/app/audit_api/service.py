from typing import Protocol

from audit_api.authorization import AuthorizedActor
from audit_api.query import AuditQuery
from audit_api.query_engine import AuditPage


class AdminAuthorizationProtocol(Protocol):
    def authorize(self, cognito_sub: str) -> AuthorizedActor: ...


class AuditQueryEngineProtocol(Protocol):
    def execute(self, query: AuditQuery) -> AuditPage: ...


class AuditQueryService:
    def __init__(
        self,
        authorization: AdminAuthorizationProtocol,
        engine: AuditQueryEngineProtocol,
    ) -> None:
        self._authorization = authorization
        self._engine = engine

    def execute(self, cognito_sub: str, query: AuditQuery) -> AuditPage:
        self._authorization.authorize(cognito_sub)
        return self._engine.execute(query)

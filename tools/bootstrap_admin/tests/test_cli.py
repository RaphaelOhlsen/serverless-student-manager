import json
from typing import Any

import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from tools.bootstrap_admin.idempotency import IdempotencyConflictError
from tools.bootstrap_admin.operational_error import (
    OperationalError,
    OperationalErrorDetails,
)
from tools.bootstrap_admin.service_models import (
    BootstrapResult,
    ResumeInvitationResult,
)
from tools.verify_first_admin_email.service import VerifyFirstAdminEmailResult

_OPERATION_ID = "17d7d774-b5b0-4c6a-9f73-16f0ff14a129"
_USER_ID = "c1220bf7-a509-4e10-b58d-d6c910445792"


class FakeBootstrapService:
    def __init__(self, outcome: BootstrapResult | BaseException) -> None:
        self._outcome = outcome
        self.calls: list[dict[str, str]] = []

    def bootstrap_first_admin(
        self,
        *,
        full_name: str,
        email: str,
        operation_id: str,
        actor_id: str,
    ) -> BootstrapResult:
        self.calls.append(
            {
                "full_name": full_name,
                "email": email,
                "operation_id": operation_id,
                "actor_id": actor_id,
            }
        )
        if isinstance(self._outcome, BaseException):
            raise self._outcome
        return self._outcome


class FakeResumeService:
    def __init__(self, outcome: ResumeInvitationResult | BaseException) -> None:
        self._outcome = outcome
        self.calls: list[dict[str, str]] = []

    def resume_first_admin_invitation(
        self,
        *,
        operation_id: str,
        actor_id: str,
    ) -> ResumeInvitationResult:
        self.calls.append(
            {
                "operation_id": operation_id,
                "actor_id": actor_id,
            }
        )
        if isinstance(self._outcome, BaseException):
            raise self._outcome
        return self._outcome


class FakeVerifyEmailService:
    def __init__(self, outcome: VerifyFirstAdminEmailResult | BaseException) -> None:
        self._outcome = outcome
        self.calls: list[dict[str, str]] = []

    def verify_first_admin_email(
        self,
        *,
        operation_id: str,
        actor_id: str,
    ) -> VerifyFirstAdminEmailResult:
        self.calls.append({"operation_id": operation_id, "actor_id": actor_id})
        if isinstance(self._outcome, BaseException):
            raise self._outcome
        return self._outcome


def _bootstrap_result(state: str = "COMPLETED") -> BootstrapResult:
    return BootstrapResult(
        operation_id=_OPERATION_ID,
        user_id=_USER_ID,
        state=state,  # type: ignore[arg-type]
        replayed=False,
    )


def _resume_result(state: str = "COMPLETED") -> ResumeInvitationResult:
    return ResumeInvitationResult(
        operation_id=_OPERATION_ID,
        state=state,  # type: ignore[arg-type]
        replayed=False,
    )


def _verify_email_result(
    state: str = "COMPLETED",
    *,
    replayed: bool = False,
) -> VerifyFirstAdminEmailResult:
    return VerifyFirstAdminEmailResult(
        operation_id=_OPERATION_ID,
        state=state,  # type: ignore[arg-type]
        replayed=replayed,
    )


def _bootstrap_args() -> list[str]:
    return [
        "bootstrap-first-admin",
        "--operation-id",
        _OPERATION_ID,
        "--actor-id",
        "github:actor@123",
        "--full-name",
        "Sensitive Name",
        "--email",
        "sensitive@example.com",
    ]


def _resume_args() -> list[str]:
    return [
        "resume-first-admin-invitation",
        "--operation-id",
        _OPERATION_ID,
        "--actor-id",
        "github:actor@123",
    ]


def _verify_email_args() -> list[str]:
    return [
        "verify-first-admin-email",
        "--operation-id",
        _OPERATION_ID,
        "--actor-id",
        "github:actor@123",
    ]


@pytest.mark.parametrize(
    "missing_option",
    ["--operation-id", "--actor-id", "--full-name", "--email"],
)
def test_bootstrap_parser_requires_every_approved_argument(
    missing_option: str,
) -> None:
    from tools.bootstrap_admin.cli import CliUsageError, build_parser

    args = _bootstrap_args()
    index = args.index(missing_option)
    del args[index : index + 2]

    with pytest.raises(CliUsageError):
        build_parser().parse_args(args)


def test_bootstrap_parser_rejects_unknown_argument() -> None:
    from tools.bootstrap_admin.cli import CliUsageError, build_parser

    with pytest.raises(CliUsageError):
        build_parser().parse_args([*_bootstrap_args(), "--user-id", _USER_ID])


@pytest.mark.parametrize("missing_option", ["--operation-id", "--actor-id"])
def test_resume_parser_requires_every_approved_argument(
    missing_option: str,
) -> None:
    from tools.bootstrap_admin.cli import CliUsageError, build_parser

    args = _resume_args()
    index = args.index(missing_option)
    del args[index : index + 2]

    with pytest.raises(CliUsageError):
        build_parser().parse_args(args)


@pytest.mark.parametrize(
    "forbidden_option",
    ["--user-id", "--email", "--full-name", "--cognito-sub"],
)
def test_resume_parser_rejects_business_identity_arguments(
    forbidden_option: str,
) -> None:
    from tools.bootstrap_admin.cli import CliUsageError, build_parser

    with pytest.raises(CliUsageError):
        build_parser().parse_args([*_resume_args(), forbidden_option, "private"])


@pytest.mark.parametrize(
    ("state", "expected_exit_code"),
    [
        ("COMPLETED", 0),
        ("COMPENSATED", 0),
        ("RECONCILIATION_REQUIRED", 2),
    ],
)
def test_bootstrap_dispatches_exact_arguments_and_emits_safe_json(
    state: str,
    expected_exit_code: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tools.bootstrap_admin.cli import run

    service = FakeBootstrapService(_bootstrap_result(state))

    exit_code = run(
        _bootstrap_args(),
        bootstrap_service_factory=lambda: service,
        resume_service_factory=_unexpected_factory,
    )

    assert exit_code == expected_exit_code
    assert service.calls == [
        {
            "full_name": "Sensitive Name",
            "email": "sensitive@example.com",
            "operation_id": _OPERATION_ID,
            "actor_id": "github:actor@123",
        }
    ]
    output = capsys.readouterr()
    assert json.loads(output.out) == {
        "operationId": _OPERATION_ID,
        "replayed": False,
        "state": state,
        "userId": _USER_ID,
    }
    assert "Sensitive Name" not in output.out
    assert "sensitive@example.com" not in output.out
    assert "cognitoSub" not in output.out
    assert output.err == ""


def test_unknown_result_state_fails_closed_without_json_or_state_disclosure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tools.bootstrap_admin.cli import run

    unknown_state = "UNEXPECTED_TERMINAL_STATE"
    service = FakeBootstrapService(_bootstrap_result(unknown_state))

    exit_code = run(
        _bootstrap_args(),
        bootstrap_service_factory=lambda: service,
        resume_service_factory=_unexpected_factory,
    )

    assert exit_code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "error: operation failed" in output.err
    assert "stage=UNCLASSIFIED_OPERATION" in output.err
    assert "exceptionClass=RuntimeError" in output.err
    assert f"operationId={_OPERATION_ID}" in output.err
    assert unknown_state not in output.err
    assert "Traceback" not in output.err


@pytest.mark.parametrize(
    ("state", "expected_exit_code"),
    [("COMPLETED", 0), ("RECONCILIATION_REQUIRED", 2)],
)
def test_resume_dispatches_only_operation_and_actor_and_emits_safe_json(
    state: str,
    expected_exit_code: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tools.bootstrap_admin.cli import run

    service = FakeResumeService(_resume_result(state))

    exit_code = run(
        _resume_args(),
        bootstrap_service_factory=_unexpected_factory,
        resume_service_factory=lambda: service,
    )

    assert exit_code == expected_exit_code
    assert service.calls == [
        {
            "operation_id": _OPERATION_ID,
            "actor_id": "github:actor@123",
        }
    ]
    output = capsys.readouterr()
    assert json.loads(output.out) == {
        "operationId": _OPERATION_ID,
        "replayed": False,
        "state": state,
    }
    assert "userId" not in output.out
    assert "email" not in output.out
    assert "cognitoSub" not in output.out
    assert output.err == ""


@pytest.mark.parametrize(
    "error",
    [
        ValueError("sensitive@example.com is invalid"),
        IdempotencyConflictError("sensitive payload conflict"),
        RuntimeError("AWS request contained sensitive@example.com"),
    ],
)
def test_errors_are_sanitized_without_traceback_or_personal_input(
    error: BaseException,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tools.bootstrap_admin.cli import run

    service = FakeBootstrapService(error)

    exit_code = run(
        _bootstrap_args(),
        bootstrap_service_factory=lambda: service,
        resume_service_factory=_unexpected_factory,
    )

    assert exit_code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "Traceback" not in output.err
    assert "Sensitive Name" not in output.err
    assert "sensitive@example.com" not in output.err
    assert "payload" not in output.err


@pytest.mark.parametrize(
    "code",
    [
        "ValidationException",
        "AccessDeniedException",
        "ResourceNotFoundException",
        "TransactionCanceledException",
    ],
)
def test_operational_client_errors_emit_safe_diagnostic(
    code: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tools.bootstrap_admin.cli import run

    cause = ClientError(
        {
            "Error": {
                "Code": code,
                "Message": "Sensitive Name sensitive@example.com",
            },
            "ResponseMetadata": {"RequestId": "request-id-123"},
        },
        "TransactWriteItems",
    )
    diagnostic = OperationalError(
        OperationalErrorDetails.from_exception(
            cause,
            stage="PERSIST_FIRST_ADMIN_TRANSACTION",
            service="dynamodb",
            operation="TransactWriteItems",
            operation_id=_OPERATION_ID,
        )
    )
    service = FakeBootstrapService(diagnostic)

    exit_code = run(
        _bootstrap_args(),
        bootstrap_service_factory=lambda: service,
        resume_service_factory=_unexpected_factory,
    )

    assert exit_code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "stage=PERSIST_FIRST_ADMIN_TRANSACTION" in output.err
    assert "service=dynamodb" in output.err
    assert "operation=TransactWriteItems" in output.err
    assert "exceptionClass=ClientError" in output.err
    assert f"awsErrorCode={code}" in output.err
    assert "awsRequestId=request-id-123" in output.err
    assert f"operationId={_OPERATION_ID}" in output.err
    assert "Sensitive Name" not in output.err
    assert "sensitive@example.com" not in output.err


def test_invalid_uuid_returns_one_without_generating_operation_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tools.bootstrap_admin.cli import run

    service = FakeResumeService(ValueError("canonical UUIDv4 required"))
    args = _resume_args()
    args[2] = "invalid-operation-id"

    assert (
        run(
            args,
            bootstrap_service_factory=_unexpected_factory,
            resume_service_factory=lambda: service,
        )
        == 1
    )
    assert service.calls[0]["operation_id"] == "invalid-operation-id"
    assert "invalid input" in capsys.readouterr().err


def test_parser_error_is_sanitized_and_returns_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tools.bootstrap_admin.cli import run

    assert (
        run(
            [*_resume_args(), "--email", "sensitive@example.com"],
            bootstrap_service_factory=_unexpected_factory,
            resume_service_factory=_unexpected_factory,
        )
        == 1
    )
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "error: invalid command arguments\n"


@pytest.mark.parametrize("missing_option", ["--operation-id", "--actor-id"])
def test_verify_email_parser_requires_operational_arguments(
    missing_option: str,
) -> None:
    from tools.bootstrap_admin.cli import CliUsageError, build_parser

    args = _verify_email_args()
    index = args.index(missing_option)
    del args[index : index + 2]

    with pytest.raises(CliUsageError):
        build_parser().parse_args(args)


@pytest.mark.parametrize(
    "forbidden_option",
    ["--email", "--full-name", "--user-id", "--cognito-sub"],
)
def test_verify_email_parser_rejects_business_identity_arguments(
    forbidden_option: str,
) -> None:
    from tools.bootstrap_admin.cli import CliUsageError, build_parser

    with pytest.raises(CliUsageError):
        build_parser().parse_args(
            [*_verify_email_args(), forbidden_option, "sensitive@example.com"]
        )


@pytest.mark.parametrize(
    ("state", "replayed", "expected_exit_code"),
    [
        ("COMPLETED", False, 0),
        ("COMPLETED", True, 0),
        ("RECONCILIATION_REQUIRED", False, 2),
    ],
)
def test_verify_email_dispatches_once_and_emits_safe_json(
    state: str,
    replayed: bool,
    expected_exit_code: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tools.bootstrap_admin.cli import run

    service = FakeVerifyEmailService(_verify_email_result(state, replayed=replayed))

    exit_code = run(
        _verify_email_args(),
        bootstrap_service_factory=_unexpected_factory,
        resume_service_factory=_unexpected_factory,
        verify_email_service_factory=lambda: service,
    )

    assert exit_code == expected_exit_code
    assert service.calls == [{"operation_id": _OPERATION_ID, "actor_id": "github:actor@123"}]
    output = capsys.readouterr()
    assert json.loads(output.out) == {
        "operationId": _OPERATION_ID,
        "replayed": replayed,
        "state": state,
    }
    assert "email" not in output.out.lower()
    assert _USER_ID not in output.out
    assert output.err == ""


@pytest.mark.parametrize(
    "error",
    [
        ValueError("admin@example.com is invalid"),
        RuntimeError("AWS request contained admin@example.com"),
        ClientError(
            {
                "Error": {
                    "Code": "AccessDeniedException",
                    "Message": "admin@example.com",
                }
            },
            "AdminUpdateUserAttributes",
        ),
    ],
)
def test_verify_email_errors_are_sanitized_and_called_once(
    error: BaseException,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tools.bootstrap_admin.cli import run

    service = FakeVerifyEmailService(error)

    assert (
        run(
            _verify_email_args(),
            bootstrap_service_factory=_unexpected_factory,
            resume_service_factory=_unexpected_factory,
            verify_email_service_factory=lambda: service,
        )
        == 1
    )
    output = capsys.readouterr()
    assert output.out == ""
    assert "admin@example.com" not in output.err
    assert "Traceback" not in output.err
    assert len(service.calls) == 1


def test_verify_email_composition_root_wires_readers_repositories_and_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tools.bootstrap_admin.cli as cli

    calls = _patch_composition_dependencies(monkeypatch, cli)

    service = cli._build_verify_email_service()

    assert service is calls["verify_email_service"]
    assert calls["clients"] == [
        ("cognito-idp", "sa-east-1"),
        ("dynamodb", "sa-east-1"),
    ]
    assert calls["tables"] == ["idempotency-table"]
    assert calls["verify_email_discovery_config"] == {
        "users_table_name": "users-table",
        "user_pool_id": "pool-id",
    }
    assert calls["verify_email_discovery"] == {
        "config": "verify-email-discovery-config",
        "provisioning_reader": ("provisioning", "dynamodb-client"),
        "cognito_reader": ("cognito", "cognito-idp-client"),
    }
    assert calls["verify_email_config"] == {
        "environment": "dev",
        "user_pool_id": "pool-id",
        "audit_table_name": "audit-table",
        "audit_retention_days": 90,
    }
    assert calls["verify_email_dependencies"] == {
        "config": "verify-email-config",
        "clock": "clock",
        "id_generator": "ids",
        "idempotency_repository": ("idempotency", "table"),
        "discovery": "verify-email-discovery",
        "cognito_repository": ("cognito", "cognito-idp-client"),
        "audit_repository": ("audit", "dynamodb-client"),
    }


def test_bootstrap_composition_root_wires_only_bootstrap_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tools.bootstrap_admin.cli as cli

    calls = _patch_composition_dependencies(monkeypatch, cli)

    service = cli._build_bootstrap_service()

    assert service is calls["bootstrap_service"]
    assert calls["clients"] == [
        ("cognito-idp", "sa-east-1"),
        ("dynamodb", "sa-east-1"),
    ]
    assert calls["resources"] == [("dynamodb", "sa-east-1")]
    assert calls["tables"] == ["idempotency-table"]
    assert calls["bootstrap_config"] == {
        "environment": "dev",
        "user_pool_id": "pool-id",
        "users_table_name": "users-table",
        "audit_table_name": "audit-table",
        "audit_retention_days": 90,
    }
    assert calls["bootstrap_dependencies"] == {
        "clock": "clock",
        "id_generator": "ids",
        "idempotency_repository": ("idempotency", "table"),
        "cognito_repository": ("cognito", "cognito-idp-client"),
        "provisioning_repository": ("provisioning", "dynamodb-client"),
    }
    assert "discovery" not in calls
    assert "resume_dependencies" not in calls


def test_resume_composition_root_reuses_cognito_reader_and_sender(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tools.bootstrap_admin.cli as cli

    calls = _patch_composition_dependencies(monkeypatch, cli)

    service = cli._build_resume_service()

    assert service is calls["resume_service"]
    assert calls["clients"] == [
        ("cognito-idp", "sa-east-1"),
        ("dynamodb", "sa-east-1"),
    ]
    assert calls["tables"] == ["idempotency-table"]
    assert calls["discovery_config"] == {
        "users_table_name": "users-table",
        "user_pool_id": "pool-id",
    }
    assert calls["discovery"] == {
        "config": "discovery-config",
        "provisioning_reader": ("provisioning", "dynamodb-client"),
        "cognito_reader": ("cognito", "cognito-idp-client"),
    }
    assert calls["resume_config"] == {
        "environment": "dev",
        "user_pool_id": "pool-id",
    }
    assert calls["resume_dependencies"] == {
        "config": "resume-config",
        "clock": "clock",
        "id_generator": "ids",
        "idempotency_repository": ("idempotency", "table"),
        "invitation_sender": ("cognito", "cognito-idp-client"),
        "discovery": "discovery",
    }
    assert "bootstrap_dependencies" not in calls
    assert "audit_table_name" not in calls
    assert "audit_retention_days" not in calls


def _unexpected_factory() -> Any:
    raise AssertionError("unexpected service factory call")


def _patch_composition_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    cli: Any,
) -> dict[str, Any]:
    calls: dict[str, Any] = {"clients": [], "resources": [], "tables": []}

    class FakeResource:
        def Table(self, table_name: str) -> str:
            calls["tables"].append(table_name)
            return "table"

    def fake_client(service_name: str, *, region_name: str) -> str:
        calls["clients"].append((service_name, region_name))
        return f"{service_name}-client"

    def fake_resource(service_name: str, *, region_name: str) -> FakeResource:
        calls["resources"].append((service_name, region_name))
        return FakeResource()

    monkeypatch.setattr(cli.boto3, "client", fake_client)
    monkeypatch.setattr(cli.boto3, "resource", fake_resource)
    monkeypatch.setattr(cli, "get_aws_region", lambda: "sa-east-1")
    monkeypatch.setattr(cli, "get_app_environment", lambda: "dev")
    monkeypatch.setattr(cli, "get_cognito_user_pool_id", lambda: "pool-id")
    monkeypatch.setattr(cli, "get_users_table_name", lambda: "users-table")
    monkeypatch.setattr(cli, "get_audit_table_name", lambda: "audit-table")
    monkeypatch.setattr(cli, "get_idempotency_table_name", lambda: "idempotency-table")
    monkeypatch.setattr(cli, "get_audit_retention_days", lambda: 90)
    monkeypatch.setattr(cli, "SystemClock", lambda: "clock")
    monkeypatch.setattr(cli, "Uuid4Generator", lambda: "ids")
    monkeypatch.setattr(
        cli,
        "CognitoRepository",
        lambda client: ("cognito", client),
    )
    monkeypatch.setattr(
        cli,
        "ProvisioningRepository",
        lambda client: ("provisioning", client),
    )
    monkeypatch.setattr(
        cli,
        "IdempotencyRepository",
        lambda table: ("idempotency", table),
    )
    monkeypatch.setattr(
        cli,
        "AuditRepository",
        lambda client: ("audit", client),
    )

    def fake_bootstrap_config(**kwargs: object) -> str:
        calls["bootstrap_config"] = kwargs
        return "bootstrap-config"

    bootstrap_service = FakeBootstrapService(_bootstrap_result())

    def fake_bootstrap_service(**kwargs: object) -> FakeBootstrapService:
        config = kwargs.pop("config")
        assert config == "bootstrap-config"
        calls["bootstrap_dependencies"] = kwargs
        calls["bootstrap_service"] = bootstrap_service
        return bootstrap_service

    def fake_discovery_config(**kwargs: object) -> str:
        calls["discovery_config"] = kwargs
        return "discovery-config"

    def fake_discovery(**kwargs: object) -> str:
        calls["discovery"] = kwargs
        return "discovery"

    def fake_resume_config(**kwargs: object) -> str:
        calls["resume_config"] = kwargs
        return "resume-config"

    resume_service = FakeResumeService(_resume_result())

    def fake_resume_service(**kwargs: object) -> FakeResumeService:
        calls["resume_dependencies"] = kwargs
        calls["resume_service"] = resume_service
        return resume_service

    monkeypatch.setattr(cli, "FirstAdminBootstrapConfig", fake_bootstrap_config)
    monkeypatch.setattr(cli, "FirstAdminBootstrapService", fake_bootstrap_service)
    monkeypatch.setattr(cli, "ResumeInvitationDiscoveryConfig", fake_discovery_config)
    monkeypatch.setattr(cli, "ResumeInvitationDiscovery", fake_discovery)
    monkeypatch.setattr(cli, "ResumeInvitationServiceConfig", fake_resume_config)
    monkeypatch.setattr(cli, "ResumeInvitationService", fake_resume_service)

    def fake_verify_email_discovery_config(**kwargs: object) -> str:
        calls["verify_email_discovery_config"] = kwargs
        return "verify-email-discovery-config"

    def fake_verify_email_discovery(**kwargs: object) -> str:
        calls["verify_email_discovery"] = kwargs
        return "verify-email-discovery"

    def fake_verify_email_config(**kwargs: object) -> str:
        calls["verify_email_config"] = kwargs
        return "verify-email-config"

    verify_email_service = FakeVerifyEmailService(_verify_email_result())

    def fake_verify_email_service(**kwargs: object) -> FakeVerifyEmailService:
        calls["verify_email_dependencies"] = kwargs
        calls["verify_email_service"] = verify_email_service
        return verify_email_service

    monkeypatch.setattr(
        cli,
        "VerifyFirstAdminEmailDiscoveryConfig",
        fake_verify_email_discovery_config,
    )
    monkeypatch.setattr(
        cli,
        "VerifyFirstAdminEmailDiscovery",
        fake_verify_email_discovery,
    )
    monkeypatch.setattr(
        cli,
        "VerifyFirstAdminEmailServiceConfig",
        fake_verify_email_config,
    )
    monkeypatch.setattr(
        cli,
        "VerifyFirstAdminEmailService",
        fake_verify_email_service,
    )
    return calls

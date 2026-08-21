import argparse
import json
import sys
from collections.abc import Callable, Sequence
from typing import Any, NoReturn, Protocol

import boto3  # type: ignore[import-untyped]

from tools.bootstrap_admin.clock import SystemClock
from tools.bootstrap_admin.cognito_repository import CognitoRepository
from tools.bootstrap_admin.config import (
    get_app_environment,
    get_audit_retention_days,
    get_audit_table_name,
    get_aws_region,
    get_cognito_user_pool_id,
    get_idempotency_table_name,
    get_users_table_name,
)
from tools.bootstrap_admin.idempotency import IdempotencyConflictError
from tools.bootstrap_admin.idempotency_repository import IdempotencyRepository
from tools.bootstrap_admin.ids import Uuid4Generator
from tools.bootstrap_admin.operational_error import (
    UNCLASSIFIED_OPERATION,
    OperationalError,
    OperationalErrorDetails,
)
from tools.bootstrap_admin.provisioning_repository import ProvisioningRepository
from tools.bootstrap_admin.resume_discovery import (
    ResumeInvitationDiscovery,
    ResumeInvitationDiscoveryConfig,
)
from tools.bootstrap_admin.resume_service import (
    ResumeInvitationService,
    ResumeInvitationServiceConfig,
)
from tools.bootstrap_admin.service import FirstAdminBootstrapService
from tools.bootstrap_admin.service_models import (
    BootstrapResult,
    FirstAdminBootstrapConfig,
    ResumeInvitationResult,
)


class BootstrapService(Protocol):
    def bootstrap_first_admin(
        self,
        *,
        full_name: str,
        email: str,
        operation_id: str,
        actor_id: str,
    ) -> BootstrapResult: ...


class ResumeService(Protocol):
    def resume_first_admin_invitation(
        self,
        *,
        operation_id: str,
        actor_id: str,
    ) -> ResumeInvitationResult: ...


class CliUsageError(ValueError):
    pass


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise CliUsageError("invalid command arguments")


def build_parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(prog="python -m tools.bootstrap_admin")
    commands = parser.add_subparsers(dest="command", required=True)

    bootstrap = commands.add_parser(
        "bootstrap-first-admin",
        help="Provision the first Administrator.",
    )
    bootstrap.add_argument("--operation-id", required=True)
    bootstrap.add_argument("--actor-id", required=True)
    bootstrap.add_argument("--full-name", required=True)
    bootstrap.add_argument("--email", required=True)

    resume = commands.add_parser(
        "resume-first-admin-invitation",
        help="Resume the first Administrator invitation.",
    )
    resume.add_argument("--operation-id", required=True)
    resume.add_argument("--actor-id", required=True)

    return parser


def _aws_dependencies() -> tuple[Any, Any, Any]:
    region = get_aws_region()
    cognito_client = boto3.client("cognito-idp", region_name=region)
    dynamodb_client = boto3.client("dynamodb", region_name=region)
    dynamodb_resource = boto3.resource("dynamodb", region_name=region)
    idempotency_table = dynamodb_resource.Table(get_idempotency_table_name())
    return cognito_client, dynamodb_client, idempotency_table


def _build_bootstrap_service() -> BootstrapService:
    cognito_client, dynamodb_client, idempotency_table = _aws_dependencies()
    return FirstAdminBootstrapService(
        config=FirstAdminBootstrapConfig(
            environment=get_app_environment(),
            user_pool_id=get_cognito_user_pool_id(),
            users_table_name=get_users_table_name(),
            audit_table_name=get_audit_table_name(),
            audit_retention_days=get_audit_retention_days(),
        ),
        clock=SystemClock(),
        id_generator=Uuid4Generator(),
        idempotency_repository=IdempotencyRepository(idempotency_table),
        cognito_repository=CognitoRepository(cognito_client),
        provisioning_repository=ProvisioningRepository(dynamodb_client),
    )


def _build_resume_service() -> ResumeService:
    cognito_client, dynamodb_client, idempotency_table = _aws_dependencies()
    cognito_repository = CognitoRepository(cognito_client)
    provisioning_repository = ProvisioningRepository(dynamodb_client)
    discovery = ResumeInvitationDiscovery(
        config=ResumeInvitationDiscoveryConfig(
            users_table_name=get_users_table_name(),
            user_pool_id=get_cognito_user_pool_id(),
        ),
        provisioning_reader=provisioning_repository,
        cognito_reader=cognito_repository,
    )
    return ResumeInvitationService(
        config=ResumeInvitationServiceConfig(
            environment=get_app_environment(),
            user_pool_id=get_cognito_user_pool_id(),
        ),
        clock=SystemClock(),
        id_generator=Uuid4Generator(),
        idempotency_repository=IdempotencyRepository(idempotency_table),
        invitation_sender=cognito_repository,
        discovery=discovery,
    )


def _bootstrap_output(result: BootstrapResult) -> dict[str, object]:
    return {
        "operationId": result.operation_id,
        "userId": result.user_id,
        "state": result.state,
        "replayed": result.replayed,
    }


def _resume_output(result: ResumeInvitationResult) -> dict[str, object]:
    return {
        "operationId": result.operation_id,
        "state": result.state,
        "replayed": result.replayed,
    }


def _write_result(result: dict[str, object]) -> None:
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


def _exit_code(state: str) -> int:
    if state in {"COMPLETED", "COMPENSATED"}:
        return 0
    if state == "RECONCILIATION_REQUIRED":
        return 2
    raise RuntimeError("unexpected terminal state")


def run(
    argv: Sequence[str],
    *,
    bootstrap_service_factory: Callable[[], BootstrapService] = _build_bootstrap_service,
    resume_service_factory: Callable[[], ResumeService] = _build_resume_service,
) -> int:
    arguments: argparse.Namespace | None = None
    try:
        arguments = build_parser().parse_args(argv)
        if arguments.command == "bootstrap-first-admin":
            bootstrap_result = bootstrap_service_factory().bootstrap_first_admin(
                full_name=arguments.full_name,
                email=arguments.email,
                operation_id=arguments.operation_id,
                actor_id=arguments.actor_id,
            )
            exit_code = _exit_code(bootstrap_result.state)
            _write_result(_bootstrap_output(bootstrap_result))
            return exit_code

        resume_result = resume_service_factory().resume_first_admin_invitation(
            operation_id=arguments.operation_id,
            actor_id=arguments.actor_id,
        )
        exit_code = _exit_code(resume_result.state)
        _write_result(_resume_output(resume_result))
        return exit_code
    except CliUsageError:
        print("error: invalid command arguments", file=sys.stderr)
    except IdempotencyConflictError:
        print("error: idempotency conflict", file=sys.stderr)
    except ValueError:
        print("error: invalid input", file=sys.stderr)
    except OperationalError as error:
        print(error.details.format_for_operator(), file=sys.stderr)
    except Exception as error:
        operation_id = getattr(arguments, "operation_id", "unavailable")
        command = getattr(arguments, "command", "unknown")
        details = OperationalErrorDetails.from_exception(
            error,
            stage=UNCLASSIFIED_OPERATION,
            service="application",
            operation=command,
            operation_id=operation_id,
        )
        print(details.format_for_operator(), file=sys.stderr)
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    return run(sys.argv[1:] if argv is None else argv)

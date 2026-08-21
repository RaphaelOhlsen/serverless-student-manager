import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from tools.bootstrap_admin.operational_error import OperationalErrorDetails

_OPERATION_ID = "123e4567-e89b-42d3-a456-426614174000"
_FULL_NAME = "Example Admin"
_EMAIL = "example-admin@example.invalid"


def _client_error(
    code: str,
    *,
    cancellation_reasons: list[dict[str, str]] | None = None,
) -> ClientError:
    response: dict[str, object] = {
        "Error": {
            "Code": code,
            "Message": f"unsafe {_FULL_NAME} {_EMAIL}",
        },
        "ResponseMetadata": {"RequestId": "request-id-123"},
    }
    if cancellation_reasons is not None:
        response["CancellationReasons"] = cancellation_reasons
    return ClientError(response, "TransactWriteItems")


@pytest.mark.parametrize(
    "code",
    [
        "ValidationException",
        "AccessDeniedException",
        "ResourceNotFoundException",
    ],
)
def test_client_error_diagnostic_contains_safe_technical_context(code: str) -> None:
    details = OperationalErrorDetails.from_exception(
        _client_error(code),
        stage="PERSIST_FIRST_ADMIN_TRANSACTION",
        service="dynamodb",
        operation="TransactWriteItems",
        operation_id=_OPERATION_ID,
    )

    output = details.format_for_operator()

    assert "stage=PERSIST_FIRST_ADMIN_TRANSACTION" in output
    assert "service=dynamodb" in output
    assert "operation=TransactWriteItems" in output
    assert "exceptionClass=ClientError" in output
    assert f"awsErrorCode={code}" in output
    assert "awsRequestId=request-id-123" in output
    assert f"operationId={_OPERATION_ID}" in output
    assert _FULL_NAME not in output
    assert _EMAIL not in output
    assert "unsafe" not in output


def test_transaction_canceled_diagnostic_includes_only_reason_codes() -> None:
    details = OperationalErrorDetails.from_exception(
        _client_error(
            "TransactionCanceledException",
            cancellation_reasons=[
                {"Code": "ConditionalCheckFailed", "Message": _EMAIL},
                {"Code": "None", "Message": _FULL_NAME},
            ],
        ),
        stage="PERSIST_FIRST_ADMIN_TRANSACTION",
        service="dynamodb",
        operation="TransactWriteItems",
        operation_id=_OPERATION_ID,
    )

    output = details.format_for_operator()

    assert "awsErrorCode=TransactionCanceledException" in output
    assert "cancellationReasonCodes=ConditionalCheckFailed" in output
    assert _FULL_NAME not in output
    assert _EMAIL not in output


def test_generic_exception_diagnostic_omits_message_and_traceback() -> None:
    error = RuntimeError(f"unsafe {_FULL_NAME} {_EMAIL}")

    output = OperationalErrorDetails.from_exception(
        error,
        stage="UNCLASSIFIED_OPERATION",
        service="application",
        operation="bootstrap-first-admin",
        operation_id=_OPERATION_ID,
    ).format_for_operator()

    assert "exceptionClass=RuntimeError" in output
    assert f"operationId={_OPERATION_ID}" in output
    assert _FULL_NAME not in output
    assert _EMAIL not in output
    assert "Traceback" not in output


def test_email_like_technical_value_is_sanitized() -> None:
    unsafe_operation_id = "sensitive@example.invalid"

    details = OperationalErrorDetails(
        stage="SAFE_STAGE",
        service="dynamodb",
        operation="TransactWriteItems",
        exception_class="ClientError",
        operation_id=unsafe_operation_id,
    )

    output = details.format_for_operator()

    assert "operationId=unavailable" in output
    assert unsafe_operation_id not in output
    assert "example.invalid" not in output


def test_untrusted_technical_metadata_cannot_inject_log_lines() -> None:
    details = OperationalErrorDetails(
        stage="SAFE_STAGE",
        service="dynamodb",
        operation="TransactWriteItems",
        exception_class="ClientError",
        operation_id="unsafe\nemail@example.invalid",
        aws_error_code="ValidationException\nunsafe",
        aws_request_id="request id with spaces",
        cancellation_reason_codes=("ConditionalCheckFailed\nunsafe",),
    )

    output = details.format_for_operator()

    assert "\n" not in output
    assert "example.invalid" not in output
    assert output.count("unavailable") == 4

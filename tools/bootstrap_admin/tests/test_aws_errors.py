import pytest
from botocore.exceptions import (
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

from tools.bootstrap_admin.aws_errors import (
    get_aws_error_code,
    is_ambiguous_aws_transport_error,
    is_ambiguous_dynamodb_write_error,
)


class AwsStyleError(Exception):
    def __init__(self, response: object) -> None:
        super().__init__("AWS operation failed")
        self.response = response


def test_get_aws_error_code_returns_string_code() -> None:
    error = AwsStyleError({"Error": {"Code": "UserNotFoundException"}})

    assert get_aws_error_code(error) == "UserNotFoundException"


def test_get_aws_error_code_returns_none_without_response() -> None:
    assert get_aws_error_code(RuntimeError("transport failed")) is None


def test_get_aws_error_code_returns_none_without_error_object() -> None:
    assert get_aws_error_code(AwsStyleError({})) is None


def test_get_aws_error_code_returns_none_for_non_string_code() -> None:
    assert get_aws_error_code(AwsStyleError({"Error": {"Code": 500}})) is None


def test_get_aws_error_code_returns_none_for_common_exception() -> None:
    assert get_aws_error_code(Exception("network timeout")) is None


@pytest.mark.parametrize(
    "error",
    [
        ConnectTimeoutError(endpoint_url="https://cognito.example"),
        ReadTimeoutError(endpoint_url="https://cognito.example"),
        ConnectionClosedError(endpoint_url="https://cognito.example"),
        EndpointConnectionError(endpoint_url="https://cognito.example"),
    ],
)
def test_selected_botocore_transport_errors_are_ambiguous(
    error: BaseException,
) -> None:
    assert is_ambiguous_aws_transport_error(error) is True


@pytest.mark.parametrize(
    "error",
    [Exception("failure"), RuntimeError("failure"), ValueError("failure")],
)
def test_common_exceptions_are_not_ambiguous_transport_errors(
    error: BaseException,
) -> None:
    assert is_ambiguous_aws_transport_error(error) is False


def _aws_error(code: str, *, http_status: int | None = None) -> AwsStyleError:
    response: dict[str, object] = {"Error": {"Code": code}}
    if http_status is not None:
        response["ResponseMetadata"] = {"HTTPStatusCode": http_status}
    return AwsStyleError(response)


def test_dynamodb_internal_server_error_is_ambiguous() -> None:
    assert is_ambiguous_dynamodb_write_error(_aws_error("InternalServerError"))


@pytest.mark.parametrize("http_status", [500, 503])
def test_unknown_dynamodb_5xx_error_is_ambiguous(http_status: int) -> None:
    assert is_ambiguous_dynamodb_write_error(
        _aws_error("UnknownServiceError", http_status=http_status)
    )


def test_unknown_dynamodb_4xx_error_is_not_ambiguous() -> None:
    assert not is_ambiguous_dynamodb_write_error(
        _aws_error("UnknownServiceError", http_status=400)
    )


@pytest.mark.parametrize(
    "code",
    [
        "TransactionCanceledException",
        "TransactionConflictException",
        "TooManyRequestsException",
        "ThrottlingException",
        "ProvisionedThroughputExceededException",
        "ValidationException",
        "AccessDeniedException",
        "ResourceNotFoundException",
    ],
)
def test_explicit_dynamodb_errors_are_not_ambiguous(code: str) -> None:
    assert not is_ambiguous_dynamodb_write_error(_aws_error(code))


def test_explicit_non_ambiguous_code_takes_precedence_over_http_5xx() -> None:
    assert not is_ambiguous_dynamodb_write_error(
        _aws_error("TransactionCanceledException", http_status=500)
    )


@pytest.mark.parametrize("error", [RuntimeError("failure"), ValueError("failure")])
def test_common_errors_are_not_ambiguous_dynamodb_writes(
    error: BaseException,
) -> None:
    assert not is_ambiguous_dynamodb_write_error(error)


@pytest.mark.parametrize(
    "error",
    [
        ConnectTimeoutError(endpoint_url="https://dynamodb.example"),
        ReadTimeoutError(endpoint_url="https://dynamodb.example"),
        ConnectionClosedError(endpoint_url="https://dynamodb.example"),
        EndpointConnectionError(endpoint_url="https://dynamodb.example"),
    ],
)
def test_selected_transport_errors_are_ambiguous_dynamodb_writes(
    error: BaseException,
) -> None:
    assert is_ambiguous_dynamodb_write_error(error)

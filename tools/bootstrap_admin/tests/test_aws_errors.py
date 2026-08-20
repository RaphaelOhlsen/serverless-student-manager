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

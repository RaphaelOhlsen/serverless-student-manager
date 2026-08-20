from botocore.exceptions import (  # type: ignore[import-untyped]
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

_AMBIGUOUS_TRANSPORT_ERRORS = (
    ConnectTimeoutError,
    ReadTimeoutError,
    ConnectionClosedError,
    EndpointConnectionError,
)

_NON_AMBIGUOUS_DYNAMODB_ERROR_CODES = {
    "TransactionCanceledException",
    "TransactionConflictException",
    "TooManyRequestsException",
    "ThrottlingException",
    "ProvisionedThroughputExceededException",
    "ValidationException",
    "AccessDeniedException",
    "ResourceNotFoundException",
}


def get_aws_error_code(error: BaseException) -> str | None:
    response: object = getattr(error, "response", None)
    if not isinstance(response, dict):
        return None

    error_details = response.get("Error")
    if not isinstance(error_details, dict):
        return None

    code = error_details.get("Code")
    return code if isinstance(code, str) else None


def is_ambiguous_aws_transport_error(error: BaseException) -> bool:
    return isinstance(error, _AMBIGUOUS_TRANSPORT_ERRORS)


def is_ambiguous_dynamodb_write_error(error: BaseException) -> bool:
    error_code = get_aws_error_code(error)
    if error_code in _NON_AMBIGUOUS_DYNAMODB_ERROR_CODES:
        return False
    if error_code == "InternalServerError":
        return True
    if is_ambiguous_aws_transport_error(error):
        return True

    response: object = getattr(error, "response", None)
    if not isinstance(response, dict):
        return False
    response_metadata = response.get("ResponseMetadata")
    if not isinstance(response_metadata, dict):
        return False
    http_status = response_metadata.get("HTTPStatusCode")
    return type(http_status) is int and 500 <= http_status <= 599

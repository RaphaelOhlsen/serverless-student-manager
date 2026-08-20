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

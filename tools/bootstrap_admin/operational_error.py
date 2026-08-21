import re
from dataclasses import dataclass

PERSIST_FIRST_ADMIN_TRANSACTION = "PERSIST_FIRST_ADMIN_TRANSACTION"
UNCLASSIFIED_OPERATION = "UNCLASSIFIED_OPERATION"
_SAFE_TECHNICAL_VALUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}")


def _sanitize_technical_value(value: str) -> str:
    return value if _SAFE_TECHNICAL_VALUE.fullmatch(value) else "unavailable"


def _response_mapping(error: BaseException) -> dict[object, object] | None:
    response: object = getattr(error, "response", None)
    return response if isinstance(response, dict) else None


def _nested_string(
    mapping: dict[object, object] | None,
    section: str,
    field: str,
) -> str | None:
    if mapping is None:
        return None
    nested = mapping.get(section)
    if not isinstance(nested, dict):
        return None
    value = nested.get(field)
    return value if isinstance(value, str) and value else None


def _cancellation_reason_codes(
    response: dict[object, object] | None,
) -> tuple[str, ...]:
    if response is None:
        return ()
    reasons = response.get("CancellationReasons")
    if not isinstance(reasons, list):
        return ()

    codes: list[str] = []
    for reason in reasons:
        if not isinstance(reason, dict):
            continue
        code = reason.get("Code")
        if isinstance(code, str) and code and code != "None":
            codes.append(code)
    return tuple(codes)


@dataclass(frozen=True)
class OperationalErrorDetails:
    stage: str
    service: str
    operation: str
    exception_class: str
    operation_id: str
    aws_error_code: str | None = None
    aws_request_id: str | None = None
    cancellation_reason_codes: tuple[str, ...] = ()

    @classmethod
    def from_exception(
        cls,
        error: BaseException,
        *,
        stage: str,
        service: str,
        operation: str,
        operation_id: str,
    ) -> "OperationalErrorDetails":
        response = _response_mapping(error)
        return cls(
            stage=stage,
            service=service,
            operation=operation,
            exception_class=type(error).__name__,
            operation_id=operation_id,
            aws_error_code=_nested_string(response, "Error", "Code"),
            aws_request_id=_nested_string(
                response,
                "ResponseMetadata",
                "RequestId",
            ),
            cancellation_reason_codes=_cancellation_reason_codes(response),
        )

    def format_for_operator(self) -> str:
        fields = [
            ("stage", self.stage),
            ("service", self.service),
            ("operation", self.operation),
            ("exceptionClass", self.exception_class),
            ("awsErrorCode", self.aws_error_code),
            ("awsRequestId", self.aws_request_id),
            ("operationId", self.operation_id),
        ]
        rendered = [
            f"{key}={_sanitize_technical_value(value)}"
            for key, value in fields
            if value is not None
        ]
        if self.cancellation_reason_codes:
            rendered.append(
                "cancellationReasonCodes="
                + ",".join(
                    _sanitize_technical_value(code) for code in self.cancellation_reason_codes
                )
            )
        return "error: operation failed " + " ".join(rendered)


class OperationalError(RuntimeError):
    def __init__(self, details: OperationalErrorDetails) -> None:
        super().__init__("operational failure")
        self.details = details

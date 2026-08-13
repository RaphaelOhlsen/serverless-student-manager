import json
from pathlib import Path
from typing import Any, cast

from aws_lambda_powertools.utilities.typing import LambdaContext
from students_api.app import lambda_handler

EVENTS_DIR = Path(__file__).resolve().parents[1] / "events"


class FakeLambdaContext:
    function_name = "StudentsApi"
    memory_limit_in_mb = 512
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:StudentsApi"
    aws_request_id = "unit-test-request"
    log_group_name = "/aws/lambda/StudentsApi"
    log_stream_name = "unit-test"

    def get_remaining_time_in_millis(self) -> int:
        return 30_000


def test_health_returns_ok() -> None:
    event = cast(
        dict[str, Any],
        json.loads((EVENTS_DIR / "health.json").read_text(encoding="utf-8")),
    )

    context = cast(LambdaContext, FakeLambdaContext())

    response = lambda_handler(event, context)

    assert response["statusCode"] == 200

    body = json.loads(cast(str, response["body"]))

    assert body == {
        "status": "ok",
        "service": "students-api",
    }

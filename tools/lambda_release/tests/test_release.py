import base64
import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from tools.lambda_release.release import ReleaseError, release

FUNCTION = "serverless-student-manager-dev-users-api"


class FakeAws:
    def __init__(self, artifact: Path, previous: str = "4") -> None:
        self.calls: list[list[str]] = []
        self.version = previous
        self.alias_revision = "alias-before"
        self.hash = base64.b64encode(hashlib.sha256(artifact.read_bytes()).digest()).decode()
        self.publishes = 0

    def __call__(self, arguments: Sequence[str]) -> dict[str, Any]:
        call = list(arguments)
        self.calls.append(call)
        operation = call[1]
        if operation == "get-function-configuration":
            qualifier = call[call.index("--qualifier") + 1] if "--qualifier" in call else "$LATEST"
            return {
                "FunctionName": FUNCTION,
                "Version": qualifier,
                "RevisionId": "function-revision",
                "CodeSha256": self.hash,
                "LastUpdateStatus": "Successful",
            }
        if operation == "get-alias":
            return {"FunctionVersion": self.version, "RevisionId": self.alias_revision}
        if operation == "update-function-code":
            return {"RevisionId": "updated-revision"}
        if operation == "wait":
            return {}
        if operation == "publish-version":
            self.publishes += 1
            return {
                "FunctionName": FUNCTION,
                "Version": str(4 + self.publishes),
                "CodeSha256": self.hash,
                "LastUpdateStatus": "Successful",
            }
        if operation == "update-alias":
            self.version = call[call.index("--function-version") + 1]
            self.alias_revision = f"alias-{self.version}"
            return {"RevisionId": self.alias_revision}
        raise AssertionError(operation)


def artifact(tmp_path: Path) -> Path:
    result = tmp_path / "api.zip"
    result.write_bytes(b"artifact")
    return result


def test_release_sequence_and_users_smoke(tmp_path: Path) -> None:
    package = artifact(tmp_path)
    aws = FakeAws(package)
    smoke_calls: list[tuple[str, str]] = []

    def smoke(method: str, url: str) -> int:
        smoke_calls.append((method, url))
        return 401

    result = release(
        api="users-api",
        function_name=FUNCTION,
        artifact=package,
        api_base_url="https://example.test",
        run=aws,
        smoke=smoke,
    )
    operations = [call[1] for call in aws.calls]
    assert result == {"previous_version": "4", "published_version": "5", "alias_version": "5"}
    assert (
        operations.index("wait")
        < operations.index("publish-version")
        < operations.index("update-alias")
    )
    assert not any("--qualifier" in call for call in aws.calls)
    assert smoke_calls == [("POST", "https://example.test/users/me/activation")]


def test_initial_latest_is_frozen_before_update(tmp_path: Path) -> None:
    package = artifact(tmp_path)
    aws = FakeAws(package, "$LATEST")
    result = release(
        api="users-api",
        function_name=FUNCTION,
        artifact=package,
        api_base_url="https://example.test",
        run=aws,
        smoke=lambda _method, _url: 401,
    )
    assert [call[1] for call in aws.calls][:5] == [
        "get-function-configuration",
        "get-alias",
        "publish-version",
        "update-alias",
        "update-function-code",
    ]
    assert result["previous_version"] == "5"


def test_failed_smoke_rolls_back(tmp_path: Path) -> None:
    package = artifact(tmp_path)
    aws = FakeAws(package)
    smoke_results = iter((500, 500, 500, 401))
    with pytest.raises(ReleaseError, match="rollback completed"):
        release(
            api="users-api",
            function_name=FUNCTION,
            artifact=package,
            api_base_url="https://example.test",
            run=aws,
            smoke=lambda _method, _url: next(smoke_results),
        )
    updates = [call for call in aws.calls if call[1] == "update-alias"]
    assert updates[-1][updates[-1].index("--function-version") + 1] == "4"


def test_failed_post_rollback_smoke_reports_rollback_failure(tmp_path: Path) -> None:
    package = artifact(tmp_path)
    aws = FakeAws(package)
    with pytest.raises(ReleaseError, match="smoke test and alias rollback failed"):
        release(
            api="users-api",
            function_name=FUNCTION,
            artifact=package,
            api_base_url="https://example.test",
            run=aws,
            smoke=lambda _method, _url: 500,
        )


def test_rejects_wrong_function_before_aws_call(tmp_path: Path) -> None:
    package = artifact(tmp_path)
    aws = FakeAws(package)
    with pytest.raises(ReleaseError):
        release(
            api="users-api",
            function_name="other",
            artifact=package,
            api_base_url="https://example.test",
            run=aws,
        )
    assert aws.calls == []

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

SUPPORTED_APIS = {"students-api", "users-api"}
SMOKE_TARGETS = {
    "students-api": ("GET", "/students"),
    "users-api": ("POST", "/users/me/activation"),
}


class ReleaseError(RuntimeError):
    pass


CommandRunner = Callable[[Sequence[str]], dict[str, Any]]
SmokeRunner = Callable[[str, str], int]


def aws_json(arguments: Sequence[str]) -> dict[str, Any]:
    completed = subprocess.run(
        ["aws", *arguments, "--output", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    if not isinstance(result, dict):
        raise ReleaseError("AWS returned an invalid response")
    return result


def smoke_status(method: str, url: str) -> int:
    request = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            return int(response.status)
    except urllib.error.HTTPError as error:
        return error.code


def _required_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReleaseError(f"AWS response omitted {name}")
    return value


def _artifact_code_sha256(artifact: Path) -> str:
    return base64.b64encode(hashlib.sha256(artifact.read_bytes()).digest()).decode("ascii")


def _validate_configuration(
    configuration: dict[str, Any], function_name: str, qualifier: str, code_sha256: str
) -> None:
    if configuration.get("FunctionName") != function_name:
        raise ReleaseError("Lambda function identity mismatch")
    if configuration.get("Version") != qualifier:
        raise ReleaseError("Lambda version mismatch")
    if configuration.get("CodeSha256") != code_sha256:
        raise ReleaseError("Lambda code hash mismatch")
    if configuration.get("LastUpdateStatus") not in {None, "Successful"}:
        raise ReleaseError("Lambda update is not successful")


def _smoke_with_retry(api: str, api_base_url: str, smoke: SmokeRunner) -> bool:
    method, path = SMOKE_TARGETS[api]
    url = f"{api_base_url.rstrip('/')}{path}"
    for attempt in range(3):
        if smoke(method, url) == 401:
            return True
        if attempt < 2:
            time.sleep(2)
    return False


def release(
    *,
    api: str,
    function_name: str,
    artifact: Path,
    api_base_url: str,
    run: CommandRunner = aws_json,
    smoke: SmokeRunner = smoke_status,
) -> dict[str, str]:
    if api not in SUPPORTED_APIS:
        raise ReleaseError("unsupported API")
    if function_name != f"serverless-student-manager-dev-{api}":
        raise ReleaseError("function name does not match API")
    if not artifact.is_file():
        raise ReleaseError("artifact does not exist")

    code_sha256 = _artifact_code_sha256(artifact)
    current = run(["lambda", "get-function-configuration", "--function-name", function_name])
    current_revision = _required_string(current.get("RevisionId"), "function RevisionId")
    alias = run(["lambda", "get-alias", "--function-name", function_name, "--name", "live"])
    alias_revision = _required_string(alias.get("RevisionId"), "alias RevisionId")
    previous_version = _required_string(alias.get("FunctionVersion"), "alias FunctionVersion")

    if previous_version == "$LATEST":
        baseline = run(
            [
                "lambda",
                "publish-version",
                "--function-name",
                function_name,
                "--revision-id",
                current_revision,
            ]
        )
        previous_version = _required_string(baseline.get("Version"), "baseline Version")
        baseline_alias = run(
            [
                "lambda",
                "update-alias",
                "--function-name",
                function_name,
                "--name",
                "live",
                "--function-version",
                previous_version,
                "--revision-id",
                alias_revision,
            ]
        )
        alias_revision = _required_string(baseline_alias.get("RevisionId"), "alias RevisionId")

    updated = run(
        [
            "lambda",
            "update-function-code",
            "--function-name",
            function_name,
            "--zip-file",
            f"fileb://{artifact}",
            "--revision-id",
            current_revision,
        ]
    )
    updated_revision = _required_string(updated.get("RevisionId"), "updated RevisionId")
    run(["lambda", "wait", "function-updated-v2", "--function-name", function_name])
    latest = run(["lambda", "get-function-configuration", "--function-name", function_name])
    _validate_configuration(latest, function_name, "$LATEST", code_sha256)

    published = run(
        [
            "lambda",
            "publish-version",
            "--function-name",
            function_name,
            "--code-sha256",
            code_sha256,
            "--revision-id",
            updated_revision,
        ]
    )
    published_version = _required_string(published.get("Version"), "published Version")
    if not published_version.isdecimal():
        raise ReleaseError("Lambda published a non-numeric version")
    _validate_configuration(published, function_name, published_version, code_sha256)

    promoted = run(
        [
            "lambda",
            "update-alias",
            "--function-name",
            function_name,
            "--name",
            "live",
            "--function-version",
            published_version,
            "--revision-id",
            alias_revision,
        ]
    )
    promoted_revision = _required_string(promoted.get("RevisionId"), "promoted RevisionId")
    try:
        confirmed = run(["lambda", "get-alias", "--function-name", function_name, "--name", "live"])
        if confirmed.get("FunctionVersion") != published_version:
            raise ReleaseError("live alias confirmation failed")
        if not _smoke_with_retry(api, api_base_url, smoke):
            raise ReleaseError("read-only smoke test failed")
    except Exception as smoke_error:
        try:
            run(
                [
                    "lambda",
                    "update-alias",
                    "--function-name",
                    function_name,
                    "--name",
                    "live",
                    "--function-version",
                    previous_version,
                    "--revision-id",
                    promoted_revision,
                ]
            )
            rolled_back = run(
                ["lambda", "get-alias", "--function-name", function_name, "--name", "live"]
            )
            if rolled_back.get("FunctionVersion") != previous_version:
                raise ReleaseError("alias rollback confirmation failed")
            if not _smoke_with_retry(api, api_base_url, smoke):
                raise ReleaseError("post-rollback smoke test failed")
        except Exception as rollback_error:
            raise ReleaseError("smoke test and alias rollback failed") from rollback_error
        raise ReleaseError("smoke test failed; alias rollback completed") from smoke_error

    return {
        "previous_version": previous_version,
        "published_version": published_version,
        "alias_version": published_version,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", required=True, choices=sorted(SUPPORTED_APIS))
    parser.add_argument("--function-name", required=True)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--output-file", required=True, type=Path)
    args = parser.parse_args()
    result = release(
        api=args.api,
        function_name=args.function_name,
        artifact=args.artifact,
        api_base_url=args.api_base_url,
    )
    with args.output_file.open("a", encoding="utf-8") as output:
        for name, value in result.items():
            output.write(f"{name}={value}\n")


if __name__ == "__main__":
    main()

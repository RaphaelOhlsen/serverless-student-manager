from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from tools.frontend_release.release import (
    ASSET_CACHE_CONTROL,
    ENTRY_POINT_CACHE_CONTROL,
    INVALIDATION_PATHS,
    STATIC_CACHE_CONTROL,
    AwsCommandError,
    HttpResponse,
    ReleaseError,
    current_index_version,
    release,
    smoke,
    upload_build,
)

BUCKET = "frontend-bucket"
DISTRIBUTION_ID = "EDISTRIBUTION"
FRONTEND_URL = "https://frontend.example"
API_BASE_URL = "https://api.example"
COMMIT_SHA = "a" * 40


class FakeAws:
    def __init__(
        self,
        *,
        previous_version: str | None = None,
        fail_operation: str | None = None,
        fail_operation_occurrence: int | None = None,
        fail_key: str | None = None,
    ) -> None:
        self.previous_version = previous_version
        self.fail_operation = fail_operation
        self.fail_operation_occurrence = fail_operation_occurrence
        self.fail_key = fail_key
        self.calls: list[list[str]] = []
        self.invalidation_count = 0
        self.operation_counts: dict[str, int] = {}

    def __call__(self, arguments: Sequence[str]) -> dict[str, Any]:
        call = list(arguments)
        self.calls.append(call)
        operation = call[1]
        self.operation_counts[operation] = self.operation_counts.get(operation, 0) + 1
        if operation == self.fail_operation and (
            self.fail_operation_occurrence is None
            or self.operation_counts[operation] == self.fail_operation_occurrence
        ):
            raise ReleaseError(f"{operation} failed")
        if operation == "put-object" and self.fail_key is not None:
            key = call[call.index("--key") + 1]
            if key == self.fail_key:
                raise ReleaseError(f"upload of {key} failed")
        if operation == "head-object":
            if self.previous_version is None:
                raise AwsCommandError(call, 254, "An error occurred (404) when calling HeadObject")
            return {"VersionId": self.previous_version}
        if operation == "put-object":
            return {"VersionId": "new-index-version"}
        if operation == "create-invalidation":
            self.invalidation_count += 1
            return {"Invalidation": {"Id": f"I{self.invalidation_count}"}}
        if operation == "wait":
            return {}
        if operation == "copy-object":
            return {"VersionId": "restored-current-version"}
        raise AssertionError(call)


class FakeHttp:
    def __init__(self, root_statuses: Sequence[int] = (200,)) -> None:
        self.root_statuses = list(root_statuses)
        self.calls: list[str] = []

    def __call__(self, url: str) -> HttpResponse:
        self.calls.append(url)
        if url == f"{FRONTEND_URL}/":
            status = self.root_statuses.pop(0)
            return HttpResponse(
                status=status,
                headers={
                    "Strict-Transport-Security": "max-age=31536000",
                    "X-Content-Type-Options": "nosniff",
                },
                body=b'<html><script src="/assets/index-abc12345.js"></script></html>',
            )
        if url == f"{FRONTEND_URL}/assets/index-abc12345.js":
            return HttpResponse(status=200, headers={}, body=b"javascript")
        if url == f"{API_BASE_URL}/health":
            return HttpResponse(status=200, headers={}, body=b'{"status":"ok"}')
        raise AssertionError(url)


def build_output(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "assets" / "index-abc12345.js").write_text("javascript", encoding="utf-8")
    (dist / "assets" / "index-def67890.css").write_text("css", encoding="utf-8")
    (dist / "favicon.svg").write_text("svg", encoding="utf-8")
    (dist / "index.html").write_text(
        '<html><script src="/assets/index-abc12345.js"></script></html>',
        encoding="utf-8",
    )
    return dist


def operations(aws: FakeAws) -> list[str]:
    return [call[1] for call in aws.calls]


def put_call_for(aws: FakeAws, key: str) -> list[str]:
    return next(
        call
        for call in aws.calls
        if call[1] == "put-object" and call[call.index("--key") + 1] == key
    )


def test_first_release_without_previous_index_succeeds(tmp_path: Path) -> None:
    aws = FakeAws()
    result = release(
        dist_dir=build_output(tmp_path),
        bucket=BUCKET,
        distribution_id=DISTRIBUTION_ID,
        frontend_url=FRONTEND_URL,
        api_base_url=API_BASE_URL,
        commit_sha=COMMIT_SHA,
        run=aws,
        get=FakeHttp(),
    )

    assert result.release_status == "SUCCESS"
    assert result.previous_index_version == "NONE"
    assert result.published_index_version == "new-index-version"
    assert "copy-object" not in operations(aws)


def test_captures_current_index_version() -> None:
    aws = FakeAws(previous_version="previous-version")
    assert current_index_version(BUCKET, aws) == "previous-version"
    assert operations(aws) == ["head-object"]


def test_missing_index_returns_none_only_for_404() -> None:
    aws = FakeAws()
    assert current_index_version(BUCKET, aws) is None


@pytest.mark.parametrize("status", ["403", "500", "ExpiredToken"])
def test_non_404_head_object_errors_are_not_silenced(status: str) -> None:
    def fail_head(arguments: Sequence[str]) -> dict[str, Any]:
        raise AwsCommandError(arguments, 254, f"An error occurred ({status}) during HeadObject")

    with pytest.raises(AwsCommandError):
        current_index_version(BUCKET, fail_head)


@pytest.mark.parametrize("version_id", [None, "null", ""])
def test_successful_head_object_requires_version_id(version_id: str | None) -> None:
    def missing_version(_arguments: Sequence[str]) -> dict[str, Any]:
        return {"ContentType": "text/html", "VersionId": version_id}

    with pytest.raises(ReleaseError, match="VersionId"):
        current_index_version(BUCKET, missing_version)


def test_uploads_assets_then_static_files_then_index(tmp_path: Path) -> None:
    aws = FakeAws(previous_version="previous-version")
    upload_build(dist_dir=build_output(tmp_path), bucket=BUCKET, commit_sha=COMMIT_SHA, run=aws)

    keys = [call[call.index("--key") + 1] for call in aws.calls]
    assert keys[:2] == ["assets/index-abc12345.js", "assets/index-def67890.css"]
    assert keys[-1] == "index.html"
    assert keys.index("favicon.svg") < keys.index("index.html")


def test_upload_cache_control_content_type_and_release_metadata(tmp_path: Path) -> None:
    aws = FakeAws(previous_version="previous-version")
    upload_build(dist_dir=build_output(tmp_path), bucket=BUCKET, commit_sha=COMMIT_SHA, run=aws)

    asset = put_call_for(aws, "assets/index-abc12345.js")
    static = put_call_for(aws, "favicon.svg")
    index = put_call_for(aws, "index.html")
    assert asset[asset.index("--cache-control") + 1] == ASSET_CACHE_CONTROL
    assert static[static.index("--cache-control") + 1] == STATIC_CACHE_CONTROL
    assert static[static.index("--content-type") + 1] == "image/svg+xml"
    assert index[index.index("--cache-control") + 1] == ENTRY_POINT_CACHE_CONTROL
    assert index[index.index("--content-type") + 1] == "text/html"
    assert index[index.index("--metadata") + 1] == f"commit-sha={COMMIT_SHA}"


def test_invalidation_uses_only_entry_points_and_waits(tmp_path: Path) -> None:
    aws = FakeAws(previous_version="previous-version")
    release(
        dist_dir=build_output(tmp_path),
        bucket=BUCKET,
        distribution_id=DISTRIBUTION_ID,
        frontend_url=FRONTEND_URL,
        api_base_url=API_BASE_URL,
        commit_sha=COMMIT_SHA,
        run=aws,
        get=FakeHttp(),
    )

    create = next(call for call in aws.calls if call[1] == "create-invalidation")
    assert create[create.index("--paths") + 1 :] == list(INVALIDATION_PATHS)
    assert operations(aws).index("create-invalidation") < operations(aws).index("wait")
    assert "/*" not in create


def test_smoke_checks_root_fingerprinted_asset_headers_and_api() -> None:
    http = FakeHttp()
    result = smoke(frontend_url=FRONTEND_URL, api_base_url=API_BASE_URL, get=http)

    assert result.asset_url == f"{FRONTEND_URL}/assets/index-abc12345.js"
    assert http.calls == [
        f"{FRONTEND_URL}/",
        f"{FRONTEND_URL}/assets/index-abc12345.js",
        f"{API_BASE_URL}/health",
    ]


def test_smoke_fails_without_managed_security_headers() -> None:
    def missing_headers(_url: str) -> HttpResponse:
        return HttpResponse(status=200, headers={}, body=b"<html></html>")

    with pytest.raises(ReleaseError, match="Strict-Transport-Security"):
        smoke(frontend_url=FRONTEND_URL, api_base_url=API_BASE_URL, get=missing_headers)


def test_smoke_failure_rolls_back_previous_version_but_release_remains_failed(
    tmp_path: Path,
) -> None:
    aws = FakeAws(previous_version="version/with+characters=")
    result = release(
        dist_dir=build_output(tmp_path),
        bucket=BUCKET,
        distribution_id=DISTRIBUTION_ID,
        frontend_url=FRONTEND_URL,
        api_base_url=API_BASE_URL,
        commit_sha=COMMIT_SHA,
        run=aws,
        get=FakeHttp(root_statuses=(500, 200)),
    )

    assert result.release_status == "RELEASE_FAILED"
    assert result.rollback_result == "ROLLBACK_EXECUTED"
    assert result.rollback_smoke_result == "PASS"
    copy = next(call for call in aws.calls if call[1] == "copy-object")
    copy_source = copy[copy.index("--copy-source") + 1]
    assert copy_source.endswith("?versionId=version%2Fwith%2Bcharacters%3D")
    assert copy[copy.index("--metadata-directive") + 1] == "COPY"
    assert operations(aws).count("create-invalidation") == 2


def test_first_release_smoke_failure_has_no_rollback(tmp_path: Path) -> None:
    aws = FakeAws()
    result = release(
        dist_dir=build_output(tmp_path),
        bucket=BUCKET,
        distribution_id=DISTRIBUTION_ID,
        frontend_url=FRONTEND_URL,
        api_base_url=API_BASE_URL,
        commit_sha=COMMIT_SHA,
        run=aws,
        get=FakeHttp(root_statuses=(500,)),
    )

    assert result.release_status == "RELEASE_FAILED"
    assert result.rollback_result == "ROLLBACK_NOT_AVAILABLE_FIRST_RELEASE"
    assert result.rollback_smoke_result == "NOT_RUN"
    assert "copy-object" not in operations(aws)


def test_failed_rollback_smoke_is_reported_and_release_remains_failed(tmp_path: Path) -> None:
    aws = FakeAws(previous_version="previous-version")
    result = release(
        dist_dir=build_output(tmp_path),
        bucket=BUCKET,
        distribution_id=DISTRIBUTION_ID,
        frontend_url=FRONTEND_URL,
        api_base_url=API_BASE_URL,
        commit_sha=COMMIT_SHA,
        run=aws,
        get=FakeHttp(root_statuses=(500, 500)),
    )

    assert result.release_status == "RELEASE_FAILED"
    assert result.rollback_result == "ROLLBACK_EXECUTED"
    assert result.rollback_smoke_result == "FAIL"


def test_asset_upload_failure_keeps_index_untouched(tmp_path: Path) -> None:
    aws = FakeAws(
        previous_version="previous-version",
        fail_key="assets/index-abc12345.js",
    )
    result = release(
        dist_dir=build_output(tmp_path),
        bucket=BUCKET,
        distribution_id=DISTRIBUTION_ID,
        frontend_url=FRONTEND_URL,
        api_base_url=API_BASE_URL,
        commit_sha=COMMIT_SHA,
        run=aws,
        get=FakeHttp(),
    )

    assert result.release_status == "RELEASE_FAILED"
    assert result.rollback_result == "NOT_REQUIRED"
    assert not any(
        call[1] == "put-object" and call[call.index("--key") + 1] == "index.html"
        for call in aws.calls
    )


def test_static_upload_failure_keeps_index_untouched(tmp_path: Path) -> None:
    aws = FakeAws(previous_version="previous-version", fail_key="favicon.svg")
    result = release(
        dist_dir=build_output(tmp_path),
        bucket=BUCKET,
        distribution_id=DISTRIBUTION_ID,
        frontend_url=FRONTEND_URL,
        api_base_url=API_BASE_URL,
        commit_sha=COMMIT_SHA,
        run=aws,
        get=FakeHttp(),
    )

    assert result.release_status == "RELEASE_FAILED"
    assert result.rollback_result == "NOT_REQUIRED"
    assert not any(
        call[1] == "put-object" and call[call.index("--key") + 1] == "index.html"
        for call in aws.calls
    )


def test_index_upload_failure_is_reported_without_false_rollback(tmp_path: Path) -> None:
    aws = FakeAws(previous_version="previous-version", fail_key="index.html")
    result = release(
        dist_dir=build_output(tmp_path),
        bucket=BUCKET,
        distribution_id=DISTRIBUTION_ID,
        frontend_url=FRONTEND_URL,
        api_base_url=API_BASE_URL,
        commit_sha=COMMIT_SHA,
        run=aws,
        get=FakeHttp(),
    )

    assert result.release_status == "RELEASE_FAILED"
    assert result.failure_stage == "UPLOAD_BUILD"
    assert result.rollback_result == "NOT_REQUIRED"


def test_initial_invalidation_failure_rolls_back_previous_index(tmp_path: Path) -> None:
    aws = FakeAws(
        previous_version="previous-version",
        fail_operation="create-invalidation",
        fail_operation_occurrence=1,
    )
    result = release(
        dist_dir=build_output(tmp_path),
        bucket=BUCKET,
        distribution_id=DISTRIBUTION_ID,
        frontend_url=FRONTEND_URL,
        api_base_url=API_BASE_URL,
        commit_sha=COMMIT_SHA,
        run=aws,
        get=FakeHttp(),
    )

    assert result.release_status == "RELEASE_FAILED"
    assert result.failure_stage == "INVALIDATION"
    assert result.rollback_result == "ROLLBACK_EXECUTED"
    assert result.rollback_smoke_result == "PASS"


def test_restore_failure_reports_degraded_state_without_rollback_smoke(tmp_path: Path) -> None:
    aws = FakeAws(previous_version="previous-version", fail_operation="copy-object")
    result = release(
        dist_dir=build_output(tmp_path),
        bucket=BUCKET,
        distribution_id=DISTRIBUTION_ID,
        frontend_url=FRONTEND_URL,
        api_base_url=API_BASE_URL,
        commit_sha=COMMIT_SHA,
        run=aws,
        get=FakeHttp(root_statuses=(500,)),
    )

    assert result.release_status == "RELEASE_FAILED"
    assert result.rollback_result == "ROLLBACK_RESTORE_FAILED"
    assert result.rollback_smoke_result == "NOT_RUN"


def test_rollback_invalidation_failure_is_distinct_from_smoke_failure(
    tmp_path: Path,
) -> None:
    aws = FakeAws(
        previous_version="previous-version",
        fail_operation="create-invalidation",
        fail_operation_occurrence=2,
    )
    result = release(
        dist_dir=build_output(tmp_path),
        bucket=BUCKET,
        distribution_id=DISTRIBUTION_ID,
        frontend_url=FRONTEND_URL,
        api_base_url=API_BASE_URL,
        commit_sha=COMMIT_SHA,
        run=aws,
        get=FakeHttp(root_statuses=(500,)),
    )

    assert result.release_status == "RELEASE_FAILED"
    assert result.rollback_result == "ROLLBACK_INVALIDATION_FAILED"
    assert result.rollback_smoke_result == "NOT_RUN"


def test_release_never_uses_delete_operations(tmp_path: Path) -> None:
    aws = FakeAws(previous_version="previous-version")
    release(
        dist_dir=build_output(tmp_path),
        bucket=BUCKET,
        distribution_id=DISTRIBUTION_ID,
        frontend_url=FRONTEND_URL,
        api_base_url=API_BASE_URL,
        commit_sha=COMMIT_SHA,
        run=aws,
        get=FakeHttp(),
    )

    assert not any(operation.startswith("delete") for operation in operations(aws))
    assert "sync" not in operations(aws)


def test_workflow_has_safe_triggers_outputs_and_no_hardcoded_hosting_ids() -> None:
    workflow = (
        Path(__file__).resolve().parents[3] / ".github/workflows/frontend-release.yml"
    ).read_text(encoding="utf-8")

    assert '      - "frontend/**"' in workflow
    assert "workflow_dispatch:" in workflow
    assert "if: github.ref == 'refs/heads/main'" in workflow
    assert "contents: read" in workflow
    assert "group: frontend-release-dev" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "id-token: write" in workflow
    assert "Repository variable TERRAFORM_STATE_BUCKET is required." in workflow
    assert "Required Terraform output ${output_name} is absent." in workflow
    assert "terraform -chdir=infra/environments/dev output -raw frontend_bucket_name" in workflow
    assert "terraform apply" not in workflow
    assert "sync --delete" not in workflow
    assert re.search(r"\bE[A-Z0-9]{13}\b", workflow) is None
    assert re.search(r"\bd[a-z0-9]+\.cloudfront\.net\b", workflow) is None
    assert re.search(r"serverless-student-manager-dev-frontend-\d{12}", workflow) is None

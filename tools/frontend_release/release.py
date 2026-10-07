from __future__ import annotations

import argparse
import json
import mimetypes
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ASSET_CACHE_CONTROL = "public,max-age=31536000,immutable"
ENTRY_POINT_CACHE_CONTROL = "no-cache"
STATIC_CACHE_CONTROL = "no-cache"
INVALIDATION_PATHS = ("/", "/index.html")
COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
FINGERPRINTED_ASSET_PATTERN = re.compile(r"/assets/[^/?#]+-[A-Za-z0-9_-]{6,}\.[^/?#]+")


class ReleaseError(RuntimeError):
    """A safe, user-facing release failure."""


class AwsCommandError(ReleaseError):
    def __init__(self, arguments: Sequence[str], returncode: int, stderr: str) -> None:
        super().__init__("AWS command failed")
        self.arguments = tuple(arguments)
        self.returncode = returncode
        self.stderr = stderr

    def is_not_found(self) -> bool:
        lowered = self.stderr.lower()
        return any(marker in lowered for marker in ("(404)", "(nosuchkey)", "(notfound)"))


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class SmokeResult:
    asset_url: str


@dataclass(frozen=True)
class ReleaseResult:
    release_status: str
    previous_index_version: str
    published_index_version: str
    invalidation_id: str
    smoke_result: str
    rollback_result: str
    rollback_smoke_result: str
    asset_url: str
    failure_stage: str


CommandRunner = Callable[[Sequence[str]], dict[str, Any]]
HttpGetter = Callable[[str], HttpResponse]


def aws_json(arguments: Sequence[str]) -> dict[str, Any]:
    command = ["aws", *arguments, "--output", "json", "--no-cli-pager"]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        raise AwsCommandError(arguments, error.returncode, error.stderr) from None

    if not completed.stdout.strip():
        return {}
    result = json.loads(completed.stdout)
    if not isinstance(result, dict):
        raise ReleaseError("AWS returned an invalid response")
    return result


def http_get(url: str) -> HttpResponse:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            return HttpResponse(
                status=int(response.status),
                headers={key.lower(): value for key, value in response.headers.items()},
                body=response.read(2_000_000),
            )
    except urllib.error.HTTPError as error:
        return HttpResponse(
            status=error.code,
            headers={key.lower(): value for key, value in error.headers.items()},
            body=error.read(2_000_000),
        )
    except urllib.error.URLError as error:
        raise ReleaseError("HTTP request failed") from error


class _AssetReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attribute_name = "src" if tag == "script" else "href" if tag == "link" else None
        if attribute_name is None:
            return
        for name, value in attrs:
            if name == attribute_name and value:
                self.references.append(value)


def _required_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value.strip().lower() == "null":
        raise ReleaseError(f"AWS response omitted {name}")
    return value


def _validate_release_inputs(
    *,
    dist_dir: Path,
    bucket: str,
    distribution_id: str,
    frontend_url: str,
    api_base_url: str,
    commit_sha: str,
) -> None:
    if not dist_dir.is_dir() or not (dist_dir / "index.html").is_file():
        raise ReleaseError("frontend build output is incomplete")
    if not bucket or not distribution_id:
        raise ReleaseError("release target is incomplete")
    if not frontend_url.startswith("https://") or not api_base_url.startswith("https://"):
        raise ReleaseError("release URLs must use HTTPS")
    if not COMMIT_SHA_PATTERN.fullmatch(commit_sha):
        raise ReleaseError("commit SHA must be a full lowercase Git SHA")


def current_index_version(bucket: str, run: CommandRunner = aws_json) -> str | None:
    try:
        response = run(["s3api", "head-object", "--bucket", bucket, "--key", "index.html"])
    except AwsCommandError as error:
        if error.is_not_found():
            return None
        raise
    return _required_string(response.get("VersionId"), "index.html VersionId")


def _content_type(path: Path) -> str:
    guessed, _encoding = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _put_object(
    *,
    path: Path,
    key: str,
    bucket: str,
    cache_control: str,
    commit_sha: str,
    run: CommandRunner,
) -> dict[str, Any]:
    return run(
        [
            "s3api",
            "put-object",
            "--bucket",
            bucket,
            "--key",
            key,
            "--body",
            str(path),
            "--content-type",
            _content_type(path),
            "--cache-control",
            cache_control,
            "--metadata",
            f"commit-sha={commit_sha}",
        ]
    )


def upload_build(
    *,
    dist_dir: Path,
    bucket: str,
    commit_sha: str,
    run: CommandRunner = aws_json,
) -> str:
    files = sorted(path for path in dist_dir.rglob("*") if path.is_file())
    index_path = dist_dir / "index.html"
    assets = [path for path in files if path.relative_to(dist_dir).parts[0] == "assets"]
    static_files = [path for path in files if path != index_path and path not in assets]

    for path in assets:
        _put_object(
            path=path,
            key=path.relative_to(dist_dir).as_posix(),
            bucket=bucket,
            cache_control=ASSET_CACHE_CONTROL,
            commit_sha=commit_sha,
            run=run,
        )
    for path in static_files:
        _put_object(
            path=path,
            key=path.relative_to(dist_dir).as_posix(),
            bucket=bucket,
            cache_control=STATIC_CACHE_CONTROL,
            commit_sha=commit_sha,
            run=run,
        )

    response = _put_object(
        path=index_path,
        key="index.html",
        bucket=bucket,
        cache_control=ENTRY_POINT_CACHE_CONTROL,
        commit_sha=commit_sha,
        run=run,
    )
    return _required_string(response.get("VersionId"), "published index.html VersionId")


def invalidate(distribution_id: str, run: CommandRunner = aws_json) -> str:
    response = run(
        [
            "cloudfront",
            "create-invalidation",
            "--distribution-id",
            distribution_id,
            "--paths",
            *INVALIDATION_PATHS,
        ]
    )
    invalidation = response.get("Invalidation")
    if not isinstance(invalidation, dict):
        raise ReleaseError("AWS response omitted CloudFront invalidation")
    invalidation_id = _required_string(invalidation.get("Id"), "invalidation Id")
    run(
        [
            "cloudfront",
            "wait",
            "invalidation-completed",
            "--distribution-id",
            distribution_id,
            "--id",
            invalidation_id,
        ]
    )
    return invalidation_id


def smoke(
    *,
    frontend_url: str,
    api_base_url: str,
    get: HttpGetter = http_get,
) -> SmokeResult:
    root_url = f"{frontend_url.rstrip('/')}/"
    root = get(root_url)
    if root.status != 200:
        raise ReleaseError("frontend root smoke failed")

    headers = {key.lower(): value for key, value in root.headers.items()}
    if not headers.get("strict-transport-security"):
        raise ReleaseError("frontend smoke omitted Strict-Transport-Security")
    if headers.get("x-content-type-options", "").lower() != "nosniff":
        raise ReleaseError("frontend smoke omitted X-Content-Type-Options")

    parser = _AssetReferenceParser()
    parser.feed(root.body.decode("utf-8"))
    asset_reference = next(
        (
            reference
            for reference in parser.references
            if FINGERPRINTED_ASSET_PATTERN.search(reference)
        ),
        None,
    )
    if asset_reference is None:
        raise ReleaseError("frontend HTML omitted a fingerprinted asset")

    asset_url = urllib.parse.urljoin(root_url, asset_reference)
    if urllib.parse.urlparse(asset_url).netloc != urllib.parse.urlparse(root_url).netloc:
        raise ReleaseError("frontend HTML referenced an external asset")
    if get(asset_url).status != 200:
        raise ReleaseError("frontend asset smoke failed")

    health_url = f"{api_base_url.rstrip('/')}/health"
    if get(health_url).status != 200:
        raise ReleaseError("API health smoke failed")
    return SmokeResult(asset_url=asset_url)


def restore_index(
    *,
    bucket: str,
    previous_version: str,
    run: CommandRunner = aws_json,
) -> str:
    copy_source = (
        urllib.parse.quote(f"{bucket}/index.html", safe="/")
        + "?versionId="
        + urllib.parse.quote(previous_version, safe="")
    )
    response = run(
        [
            "s3api",
            "copy-object",
            "--bucket",
            bucket,
            "--key",
            "index.html",
            "--copy-source",
            copy_source,
            "--metadata-directive",
            "COPY",
        ]
    )
    return _required_string(response.get("VersionId"), "restored index.html VersionId")


def release(
    *,
    dist_dir: Path,
    bucket: str,
    distribution_id: str,
    frontend_url: str,
    api_base_url: str,
    commit_sha: str,
    run: CommandRunner = aws_json,
    get: HttpGetter = http_get,
) -> ReleaseResult:
    _validate_release_inputs(
        dist_dir=dist_dir,
        bucket=bucket,
        distribution_id=distribution_id,
        frontend_url=frontend_url,
        api_base_url=api_base_url,
        commit_sha=commit_sha,
    )
    previous_version: str | None = None
    published_version = "NONE"
    invalidation_id = "NONE"
    index_published = False
    stage = "CAPTURE_PREVIOUS_INDEX"

    try:
        previous_version = current_index_version(bucket, run)
        stage = "UPLOAD_BUILD"
        published_version = upload_build(
            dist_dir=dist_dir,
            bucket=bucket,
            commit_sha=commit_sha,
            run=run,
        )
        index_published = True
        stage = "INVALIDATION"
        invalidation_id = invalidate(distribution_id, run)
        stage = "SMOKE"
        smoke_result = smoke(frontend_url=frontend_url, api_base_url=api_base_url, get=get)
        return ReleaseResult(
            release_status="SUCCESS",
            previous_index_version=previous_version or "NONE",
            published_index_version=published_version,
            invalidation_id=invalidation_id,
            smoke_result="PASS",
            rollback_result="NOT_REQUIRED",
            rollback_smoke_result="NOT_RUN",
            asset_url=smoke_result.asset_url,
            failure_stage="NONE",
        )
    except (ReleaseError, OSError, ValueError):
        rollback_result = "NOT_REQUIRED"
        rollback_smoke_result = "NOT_RUN"
        asset_url = "NONE"

        if index_published and previous_version is None:
            rollback_result = "ROLLBACK_NOT_AVAILABLE_FIRST_RELEASE"
        elif index_published and previous_version is not None:
            try:
                restore_index(bucket=bucket, previous_version=previous_version, run=run)
            except (ReleaseError, OSError, ValueError):
                rollback_result = "ROLLBACK_RESTORE_FAILED"
            else:
                rollback_result = "ROLLBACK_EXECUTED"
                try:
                    invalidate(distribution_id, run)
                except (ReleaseError, OSError, ValueError):
                    rollback_result = "ROLLBACK_INVALIDATION_FAILED"
                else:
                    try:
                        rollback_smoke = smoke(
                            frontend_url=frontend_url,
                            api_base_url=api_base_url,
                            get=get,
                        )
                        rollback_smoke_result = "PASS"
                        asset_url = rollback_smoke.asset_url
                    except (ReleaseError, OSError, ValueError):
                        rollback_smoke_result = "FAIL"

        return ReleaseResult(
            release_status="RELEASE_FAILED",
            previous_index_version=previous_version or "NONE",
            published_index_version=published_version,
            invalidation_id=invalidation_id,
            smoke_result="FAIL" if stage == "SMOKE" else "NOT_RUN",
            rollback_result=rollback_result,
            rollback_smoke_result=rollback_smoke_result,
            asset_url=asset_url,
            failure_stage=stage,
        )


def _write_outputs(path: Path, result: ReleaseResult) -> None:
    values = asdict(result)
    with path.open("a", encoding="utf-8") as output:
        for key, value in values.items():
            output.write(f"{key}={value}\n")


def _write_summary(path: Path, commit_sha: str, result: ReleaseResult) -> None:
    with path.open("a", encoding="utf-8") as summary:
        summary.write("### Frontend release\n")
        summary.write("- environment: dev\n")
        summary.write(f"- commit: `{commit_sha}`\n")
        summary.write(f"- result: **{result.release_status}**\n")
        summary.write(f"- previous index version: `{result.previous_index_version}`\n")
        summary.write(f"- published index version: `{result.published_index_version}`\n")
        summary.write(f"- invalidation: `{result.invalidation_id}`\n")
        summary.write(f"- smoke: **{result.smoke_result}**\n")
        summary.write(f"- rollback: **{result.rollback_result}**\n")
        summary.write(f"- rollback smoke: **{result.rollback_smoke_result}**\n")
        summary.write(f"- failure stage: `{result.failure_stage}`\n")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Release the frontend to dev.")
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--distribution-id", required=True)
    parser.add_argument("--frontend-url", required=True)
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--output-file", type=Path, required=True)
    parser.add_argument("--summary-file", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = release(
            dist_dir=args.dist_dir,
            bucket=args.bucket,
            distribution_id=args.distribution_id,
            frontend_url=args.frontend_url,
            api_base_url=args.api_base_url,
            commit_sha=args.commit_sha,
        )
    except ReleaseError:
        result = ReleaseResult(
            release_status="RELEASE_FAILED",
            previous_index_version="UNKNOWN",
            published_index_version="NONE",
            invalidation_id="NONE",
            smoke_result="NOT_RUN",
            rollback_result="NOT_REQUIRED",
            rollback_smoke_result="NOT_RUN",
            asset_url="NONE",
            failure_stage="VALIDATION",
        )
    _write_outputs(args.output_file, result)
    _write_summary(args.summary_file, args.commit_sha, result)
    print(json.dumps(asdict(result), sort_keys=True))
    return 0 if result.release_status == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

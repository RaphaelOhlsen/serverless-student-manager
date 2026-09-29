#!/usr/bin/env python3
"""Classify deterministic downstream effects of a proposed protected-branch push."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import NoReturn


SCHEMA_VERSION = 1
WORKFLOW_PREFIX = ".github/workflows/"
WORKFLOW_SUFFIXES = (".yml", ".yaml")


class EvidenceError(RuntimeError):
    """Raised when safe classification is impossible."""


@dataclass(frozen=True)
class PushTrigger:
    branches: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    paths_ignore: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowMatch:
    path: str
    matched_paths: tuple[str, ...]
    mutations: tuple[str, ...]
    potentially_mutating: bool


@dataclass
class Report:
    base_ref: str
    head_ref: str
    target_branch: str
    event: str
    base_sha: str | None = None
    head_sha: str | None = None
    changed_files: list[str] = field(default_factory=list)
    matches: list[WorkflowMatch] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify merge-triggered workflow side effects without executing them."
    )
    parser.add_argument("--base", required=True, help="Base commit/ref")
    parser.add_argument("--head", default="HEAD", help="Proposed head commit/ref")
    parser.add_argument("--target-branch", default="main")
    parser.add_argument("--event", default="push")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def git(*arguments: str, text: bool = True) -> str | bytes:
    process = subprocess.run(
        ["git", *arguments],
        capture_output=True,
        check=False,
        text=text,
        env={**os.environ, "LC_ALL": "C", "GIT_OPTIONAL_LOCKS": "0"},
    )
    if process.returncode != 0:
        stderr = process.stderr if text else process.stderr.decode("utf-8", "replace")
        raise EvidenceError(f"git_command_failed:{arguments[0]}:{stderr.strip()[:120]}")
    return process.stdout


def resolve_commit(ref: str, label: str) -> str:
    try:
        value = str(git("rev-parse", "--verify", f"{ref}^{{commit}}")).strip()
    except EvidenceError as error:
        raise EvidenceError(f"{label}_missing") from error
    if not re.fullmatch(r"[0-9a-f]{40,64}", value):
        raise EvidenceError(f"{label}_invalid")
    return value


def changed_files(base_sha: str, head_sha: str) -> list[str]:
    raw = bytes(
        git(
            "diff",
            "--name-only",
            "--no-renames",
            "-z",
            base_sha,
            head_sha,
            "--",
            text=False,
        )
    )
    return sorted({part.decode("utf-8", "strict") for part in raw.split(b"\0") if part})


def workflow_paths(head_sha: str) -> list[str]:
    raw = bytes(
        git(
            "ls-tree",
            "-r",
            "--name-only",
            "-z",
            head_sha,
            "--",
            WORKFLOW_PREFIX,
            text=False,
        )
    )
    paths = sorted({part.decode("utf-8", "strict") for part in raw.split(b"\0") if part})
    return [path for path in paths if path.endswith(WORKFLOW_SUFFIXES)]


def workflow_content(head_sha: str, path: str) -> str:
    raw = bytes(git("show", f"{head_sha}:{path}", text=False))
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise EvidenceError(f"workflow_not_utf8:{path}") from error


def strip_comment(line: str) -> str:
    single_quoted = False
    double_quoted = False
    escaped = False
    output: list[str] = []
    for character in line:
        if escaped:
            output.append(character)
            escaped = False
            continue
        if character == "\\" and double_quoted:
            output.append(character)
            escaped = True
            continue
        if character == "'" and not double_quoted:
            single_quoted = not single_quoted
        elif character == '"' and not single_quoted:
            double_quoted = not double_quoted
        elif character == "#" and not single_quoted and not double_quoted:
            break
        output.append(character)
    return "".join(output).rstrip()


def scalar(value: str) -> str:
    value = value.strip()
    if not value or any(token in value for token in ("{", "}", "[", "]")):
        raise EvidenceError("unsupported_yaml_scalar")
    if value[0:1] == value[-1:] and value.startswith(("'", '"')):
        if value.startswith("'"):
            return value[1:-1].replace("''", "'")
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as error:
            raise EvidenceError("invalid_yaml_string") from error
        if not isinstance(decoded, str):
            raise EvidenceError("invalid_yaml_string")
        return decoded
    if value.startswith(("'", '"', "&", "*")) or value.endswith(("'", '"')):
        raise EvidenceError("invalid_yaml_string")
    return value


def parse_push_trigger(content: str, path: str) -> PushTrigger | None:
    logical_lines: list[tuple[int, str]] = []
    for number, original in enumerate(content.splitlines(), start=1):
        if "\t" in original[: len(original) - len(original.lstrip())]:
            raise EvidenceError(f"workflow_tab_indentation:{path}:{number}")
        line = strip_comment(original)
        if not line.strip() or line.lstrip().startswith("---"):
            continue
        indentation = len(line) - len(line.lstrip(" "))
        logical_lines.append((indentation, line.strip()))

    on_indexes = [
        index
        for index, (indentation, value) in enumerate(logical_lines)
        if indentation == 0 and value in ("on:", "'on':", '"on":')
    ]
    if len(on_indexes) != 1:
        raise EvidenceError(f"workflow_on_block_invalid:{path}")

    start = on_indexes[0] + 1
    end = len(logical_lines)
    for index in range(start, len(logical_lines)):
        if logical_lines[index][0] == 0:
            end = index
            break
    on_block = logical_lines[start:end]
    if not on_block:
        raise EvidenceError(f"workflow_on_block_empty:{path}")

    push_indexes = [
        index
        for index, (indentation, value) in enumerate(on_block)
        if indentation == 2 and value == "push:"
    ]
    if not push_indexes:
        return None
    if len(push_indexes) != 1:
        raise EvidenceError(f"workflow_push_block_invalid:{path}")

    push_start = push_indexes[0] + 1
    push_end = len(on_block)
    for index in range(push_start, len(on_block)):
        if on_block[index][0] <= 2:
            push_end = index
            break
    push_block = on_block[push_start:push_end]
    if not push_block:
        return PushTrigger()

    supported = {"branches", "paths", "paths-ignore"}
    values: dict[str, list[str]] = {key: [] for key in supported}
    current_key: str | None = None
    for indentation, value in push_block:
        if indentation == 4 and value.endswith(":"):
            key = value[:-1]
            if key not in supported or values[key]:
                raise EvidenceError(f"workflow_push_key_unsupported:{path}:{key}")
            current_key = key
            continue
        if indentation >= 6 and value.startswith("- ") and current_key is not None:
            item = scalar(value[2:])
            if item.startswith("!") or any(character in item for character in "[]"):
                raise EvidenceError(f"workflow_glob_unsupported:{path}:{current_key}")
            values[current_key].append(item)
            continue
        raise EvidenceError(f"workflow_push_structure_unsupported:{path}")

    if values["paths"] and values["paths-ignore"]:
        raise EvidenceError(f"workflow_paths_conflict:{path}")
    return PushTrigger(
        branches=tuple(values["branches"]),
        paths=tuple(values["paths"]),
        paths_ignore=tuple(values["paths-ignore"]),
    )


def glob_regex(pattern: str) -> re.Pattern[str]:
    output = ["^"]
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                output.append(".*")
                index += 2
            else:
                output.append("[^/]*")
                index += 1
        elif character == "?":
            output.append("[^/]")
            index += 1
        else:
            output.append(re.escape(character))
            index += 1
    output.append("$")
    return re.compile("".join(output))


def matches_any(value: str, patterns: tuple[str, ...]) -> bool:
    return any(glob_regex(pattern).fullmatch(value) for pattern in patterns)


def trigger_matches(
    trigger: PushTrigger, target_branch: str, files: list[str]
) -> tuple[str, ...]:
    if trigger.branches and not matches_any(target_branch, trigger.branches):
        return ()
    if trigger.paths:
        return tuple(file for file in files if matches_any(file, trigger.paths))
    if trigger.paths_ignore:
        included = tuple(
            file for file in files if not matches_any(file, trigger.paths_ignore)
        )
        return included
    return tuple(files)


KNOWN_MUTATIONS: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
    (
        "AWS_LAMBDA_RELEASE",
        (
            re.compile(r"tools/lambda_release/release\.py"),
            re.compile(r"aws\s+lambda\s+(?:update-function-code|publish-version|update-alias)\b"),
        ),
    ),
    ("TERRAFORM_APPLY", (re.compile(r"terraform(?:\s+-[^\s]+)*\s+apply\b"),)),
    (
        "AWS_INFRASTRUCTURE_DEPLOY",
        (
            re.compile(r"\b(?:sam|cdk)\s+deploy\b"),
            re.compile(r"aws\s+cloudformation\s+(?:deploy|create-stack|update-stack|delete-stack)\b"),
        ),
    ),
    (
        "CONTAINER_PUBLICATION",
        (
            re.compile(r"\bdocker\s+push\b"),
            re.compile(r"\bdocker\s+buildx\s+build\b[^\n]*\s--push\b"),
        ),
    ),
    (
        "PACKAGE_OR_RELEASE_PUBLICATION",
        (
            re.compile(r"\b(?:npm\s+publish|twine\s+upload|gh\s+release\s+create)\b"),
        ),
    ),
    (
        "AWS_MUTATION",
        (
            re.compile(
                r"aws\s+(?:s3\s+(?:cp|mv|rm|sync)|dynamodb\s+(?:put-item|update-item|delete-item|batch-write-item)|cognito-idp\s+(?:admin-create-user|admin-update-user-attributes|admin-delete-user))\b"
            ),
        ),
    ),
)


def classify_workflow(content: str) -> tuple[tuple[str, ...], bool]:
    mutations = tuple(
        name
        for name, patterns in KNOWN_MUTATIONS
        if any(pattern.search(content) for pattern in patterns)
    )
    if mutations:
        return mutations, False

    has_aws_credentials = "aws-actions/configure-aws-credentials@" in content
    if not has_aws_credentials:
        return (), False

    aws_commands = re.findall(r"(?m)\brun:\s*(aws\s+[^\n]+)$", content)
    safe_aws_commands = all(
        re.match(r"aws\s+sts\s+get-caller-identity(?:\s|$)", command)
        for command in aws_commands
    )
    operational_commands = re.findall(
        r"(?m)\brun:\s*(?:python(?:3)?|\./|bash\s+|sh\s+)([^\n]*)$", content
    )
    potentially_mutating = not aws_commands or not safe_aws_commands or bool(
        operational_commands
    )
    return (), potentially_mutating


def analyze(report: Report) -> None:
    report.base_sha = resolve_commit(report.base_ref, "base")
    report.head_sha = resolve_commit(report.head_ref, "head")
    try:
        git("cat-file", "-e", f"{report.head_sha}:AGENTS.md")
    except EvidenceError as error:
        raise EvidenceError("invalid_repository") from error
    if report.event != "push":
        raise EvidenceError("unsupported_event")
    report.changed_files = changed_files(report.base_sha, report.head_sha)

    for path in workflow_paths(report.head_sha):
        content = workflow_content(report.head_sha, path)
        trigger = parse_push_trigger(content, path)
        if trigger is None:
            continue
        matched_paths = trigger_matches(trigger, report.target_branch, report.changed_files)
        if not matched_paths:
            continue
        mutations, potentially_mutating = classify_workflow(content)
        report.matches.append(
            WorkflowMatch(path, matched_paths, mutations, potentially_mutating)
        )


def outcome(report: Report) -> tuple[str, int, list[str], bool]:
    if report.errors:
        return "INCONCLUSIVE", 2, ["UNKNOWN"], True
    mutations = sorted(
        {
            mutation
            for match in report.matches
            for mutation in match.mutations
        }
    )
    if any(match.potentially_mutating for match in report.matches):
        mutations.append("UNKNOWN_EXTERNAL_MUTATION")
    if mutations:
        return "BLOCKED", 1, mutations, True
    return "PASS", 0, ["NONE"], False


def print_text(report: Report) -> int:
    result, exit_code, mutations, release_boundary = outcome(report)
    print(f"BASE_REF={report.base_ref}")
    print(f"BASE_SHA={report.base_sha or ''}")
    print(f"HEAD_REF={report.head_ref}")
    print(f"HEAD_SHA={report.head_sha or ''}")
    print(f"TRIGGER_EVENT={report.event}")
    print(f"TRIGGER_BRANCH={report.target_branch}")
    print(f"CHANGED_FILE_COUNT={len(report.changed_files)}")
    for path in report.changed_files:
        print(f"CHANGED_FILE={json.dumps(path) if any(ord(c) < 32 for c in path) else path}")
    print(f"MATCHED_WORKFLOW_COUNT={len(report.matches)}")
    for match in sorted(report.matches, key=lambda item: item.path):
        print(f"MATCHED_WORKFLOW={match.path}")
        for path in match.matched_paths:
            print(f"MATCHED_PATH={path}")
    for mutation in mutations:
        print(f"EXTERNAL_MUTATION={mutation}")
    print(
        "EXPLICIT_RELEASE_AUTHORIZATION_REQUIRED="
        + ("YES" if release_boundary else "NO")
    )
    print("MERGE_IS_RELEASE_BOUNDARY=" + ("YES" if release_boundary else "NO"))
    print("AUTHORIZATION_GRANTED=no")
    for error in report.errors:
        print(f"ERROR={error}")
    print(f"MERGE_SIDE_EFFECT_GUARD={result}")
    return exit_code


def print_json(report: Report) -> int:
    result, exit_code, mutations, release_boundary = outcome(report)
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "tool": "agentic-merge-side-effect-guard",
        "result": result,
        "base": {"ref": report.base_ref, "sha": report.base_sha},
        "head": {"ref": report.head_ref, "sha": report.head_sha},
        "trigger": {"event": report.event, "branch": report.target_branch},
        "changedFiles": report.changed_files,
        "matches": [
            {
                "workflow": match.path,
                "matchedPaths": list(match.matched_paths),
                "mutations": list(match.mutations),
                "potentiallyMutating": match.potentially_mutating,
            }
            for match in sorted(report.matches, key=lambda item: item.path)
        ],
        "externalMutations": mutations,
        "explicitReleaseAuthorizationRequired": release_boundary,
        "mergeIsReleaseBoundary": release_boundary,
        "authorizationGranted": False,
        "errors": report.errors,
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return exit_code


def main() -> NoReturn:
    arguments = parse_arguments()
    report = Report(
        base_ref=arguments.base,
        head_ref=arguments.head,
        target_branch=arguments.target_branch,
        event=arguments.event,
    )
    try:
        root = str(git("rev-parse", "--show-toplevel")).strip()
        if not root or Path(root).name != "serverless-student-manager":
            raise EvidenceError("invalid_repository")
        analyze(report)
    except (EvidenceError, UnicodeDecodeError) as error:
        report.errors.append(str(error) or type(error).__name__)

    if arguments.format == "json":
        raise SystemExit(print_json(report))
    raise SystemExit(print_text(report))


if __name__ == "__main__":
    main()

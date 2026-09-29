from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PR_HISTORY_GUARD = PROJECT_ROOT / "scripts" / "agentic-pr-history-guard.sh"
MERGE_SIDE_EFFECT_GUARD = (
    PROJECT_ROOT / "scripts" / "agentic-merge-side-effect-guard.py"
)


class TemporaryGitRepository:
    def __init__(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary_directory.name) / "serverless-student-manager"
        self.root.mkdir()
        self.git("init", "--initial-branch=main")
        self.git("config", "user.name", "Harness Tests")
        self.git("config", "user.email", "harness@example.invalid")
        self.write("AGENTS.md", "# AGENTS.md — Serverless Student Manager\n")
        self.write("README.md", "baseline\n")
        self.commit_all("initial")
        self.initial = self.head

    def close(self) -> None:
        self._temporary_directory.cleanup()

    def git(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=check,
            env={**os.environ, "LC_ALL": "C"},
        )

    @property
    def head(self) -> str:
        return self.git("rev-parse", "HEAD").stdout.strip()

    def write(self, relative_path: str, content: str) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def commit_all(self, message: str) -> str:
        self.git("add", "--all")
        self.git("commit", "-m", message)
        return self.head

    def run(self, tool: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        command = [str(tool), *arguments]
        if tool.suffix == ".py":
            command.insert(0, sys.executable)
        return subprocess.run(
            command,
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "LC_ALL": "C"},
        )

    def snapshot(self) -> tuple[str, bytes, dict[str, str]]:
        status = self.git("status", "--porcelain=v2", "-z").stdout.encode()
        files = {
            str(path.relative_to(self.root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(self.root.rglob("*"))
            if path.is_file() and ".git" not in path.parts
        }
        return self.head, status, files


class RepositoryTestCase(unittest.TestCase):
    repo: TemporaryGitRepository

    def setUp(self) -> None:
        self.repo = TemporaryGitRepository()

    def tearDown(self) -> None:
        self.repo.close()


class PrHistoryGuardTests(RepositoryTestCase):
    def run_guard(self, base: str, head: str | None = None, output: str = "text"):
        arguments = ["--base", base, "--format", output]
        if head is not None:
            arguments[2:2] = ["--head", head]
        return self.repo.run(PR_HISTORY_GUARD, *arguments)

    def test_clean_one_commit_ahead_has_equal_file_sets(self) -> None:
        self.repo.git("switch", "-c", "feature/clean")
        self.repo.write("change.txt", "change\n")
        head = self.repo.commit_all("change")

        result = self.run_guard(self.repo.initial, head)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AHEAD=1", result.stdout)
        self.assertIn("BEHIND=0", result.stdout)
        self.assertIn("FILE_SETS_EQUAL=YES", result.stdout)
        self.assertIn("PR_HISTORY_GUARD=PASS", result.stdout)

    def test_equal_direct_and_three_dot_sets_support_spaces(self) -> None:
        self.repo.git("switch", "-c", "feature/spaces")
        self.repo.write("directory/file with spaces.txt", "change\n")
        head = self.repo.commit_all("change")

        payload = json.loads(self.run_guard(self.repo.initial, head, "json").stdout)

        self.assertEqual(payload["directFiles"], payload["threeDotFiles"])
        self.assertEqual(payload["directFiles"], ["directory/file with spaces.txt"])

    def make_squash_divergence(self) -> tuple[str, str]:
        self.repo.git("switch", "-c", "feature/legacy", self.repo.initial)
        self.repo.write("already-merged.txt", "same content\n")
        self.repo.commit_all("legacy milestone")
        self.repo.write("hardening.txt", "hardening\n")
        feature_head = self.repo.commit_all("hardening")
        self.repo.git("switch", "main")
        self.repo.write("already-merged.txt", "same content\n")
        base = self.repo.commit_all("squashed milestone")
        return base, feature_head

    def test_squash_history_divergence_is_detected(self) -> None:
        base, head = self.make_squash_divergence()

        result = self.run_guard(base, head)

        self.assertEqual(result.returncode, 1)
        self.assertIn("AHEAD=2", result.stdout)
        self.assertIn("BEHIND=1", result.stdout)
        self.assertIn("DIRECT_DIFF_FILE_COUNT=1", result.stdout)
        self.assertIn("THREE_DOT_DIFF_FILE_COUNT=2", result.stdout)
        self.assertIn("REASON=SQUASH_HISTORY_DIVERGENCE", result.stdout)
        self.assertIn("RECOMMENDED_ACTION=CREATE_FRESH_BRANCH_FROM_BASE", result.stdout)

    def test_direct_small_three_dot_polluted_reports_extra_file(self) -> None:
        base, head = self.make_squash_divergence()

        payload = json.loads(self.run_guard(base, head, "json").stdout)

        self.assertEqual(payload["directFiles"], ["hardening.txt"])
        self.assertEqual(
            payload["threeDotOnlyFiles"], ["already-merged.txt"]
        )
        self.assertFalse(payload["fileSetsEqual"])

    def test_scope_divergence_without_ahead_behind_is_classified(self) -> None:
        self.repo.git("switch", "-c", "feature/diverged")
        self.repo.write("feature.txt", "feature\n")
        head = self.repo.commit_all("feature")
        self.repo.git("switch", "main")
        self.repo.write("main.txt", "main\n")
        base = self.repo.commit_all("main")

        result = self.run_guard(base, head)

        self.assertEqual(result.returncode, 1)
        self.assertIn("DIRECT_ONLY_FILE=main.txt", result.stdout)
        self.assertIn("REASON=PR_SCOPE_DIVERGENCE", result.stdout)

    def test_no_changes_is_safe_and_explicit(self) -> None:
        result = self.run_guard(self.repo.initial, self.repo.initial)

        self.assertEqual(result.returncode, 0)
        self.assertIn("REASON=NO_CHANGES", result.stdout)
        self.assertIn("RECOMMENDED_ACTION=NO_PR_REQUIRED", result.stdout)

    def test_invalid_base_fails_inconclusive(self) -> None:
        result = self.run_guard("missing-ref")

        self.assertEqual(result.returncode, 2)
        self.assertIn("ERROR=base_missing", result.stdout)
        self.assertIn("PR_HISTORY_GUARD=INCONCLUSIVE", result.stdout)

    def test_guard_does_not_mutate_repository(self) -> None:
        self.repo.git("switch", "-c", "feature/read-only")
        self.repo.write("untracked.txt", "local\n")
        before = self.repo.snapshot()

        result = self.run_guard(self.repo.initial)
        after = self.repo.snapshot()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, after)


def workflow(
    *,
    paths: tuple[str, ...] = ("backend/**",),
    branches: tuple[str, ...] = ("main",),
    paths_ignore: tuple[str, ...] = (),
    body: str = "      - run: python -m unittest\n",
) -> str:
    lines = ["name: Fixture", "", "on:", "  push:"]
    if branches:
        lines.append("    branches:")
        lines.extend(f'      - "{item}"' for item in branches)
    if paths:
        lines.append("    paths:")
        lines.extend(f'      - "{item}"' for item in paths)
    if paths_ignore:
        lines.append("    paths-ignore:")
        lines.extend(f'      - "{item}"' for item in paths_ignore)
    lines.extend(("", "jobs:", "  fixture:", "    steps:"))
    return "\n".join(lines) + "\n" + body


class MergeSideEffectGuardTests(RepositoryTestCase):
    def commit_workflow(self, name: str, content: str) -> str:
        self.repo.write(f".github/workflows/{name}.yml", content)
        return self.repo.commit_all(f"add {name} workflow")

    def change(self, path: str = "backend/audit-api/app.py") -> tuple[str, str]:
        base = self.repo.head
        self.repo.write(path, "change\n")
        return base, self.repo.commit_all("proposed change")

    def run_guard(
        self,
        base: str,
        head: str,
        *,
        branch: str = "main",
        output: str = "text",
    ) -> subprocess.CompletedProcess[str]:
        return self.repo.run(
            MERGE_SIDE_EFFECT_GUARD,
            "--base",
            base,
            "--head",
            head,
            "--target-branch",
            branch,
            "--event",
            "push",
            "--format",
            output,
        )

    def test_no_applicable_deployment_workflow_passes(self) -> None:
        self.commit_workflow("release", workflow(paths=("frontend/**",)))
        base, head = self.change()

        result = self.run_guard(base, head)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("MATCHED_WORKFLOW_COUNT=0", result.stdout)
        self.assertIn("EXTERNAL_MUTATION=NONE", result.stdout)
        self.assertIn("MERGE_IS_RELEASE_BOUNDARY=NO", result.stdout)

    def test_lambda_release_on_main_is_blocked(self) -> None:
        body = """      - uses: aws-actions/configure-aws-credentials@v6
      - run: python tools/lambda_release/release.py --api audit-api
"""
        self.commit_workflow(
            "lambda-release", workflow(paths=("backend/audit-api/**",), body=body)
        )
        base, head = self.change("backend/audit-api/query.py")

        result = self.run_guard(base, head)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("MATCHED_WORKFLOW=.github/workflows/lambda-release.yml", result.stdout)
        self.assertIn("EXTERNAL_MUTATION=AWS_LAMBDA_RELEASE", result.stdout)
        self.assertIn("EXPLICIT_RELEASE_AUTHORIZATION_REQUIRED=YES", result.stdout)
        self.assertIn("MERGE_IS_RELEASE_BOUNDARY=YES", result.stdout)
        self.assertIn("AUTHORIZATION_GRANTED=no", result.stdout)
        self.assertIn("MERGE_SIDE_EFFECT_GUARD=BLOCKED", result.stdout)

    def test_feature_branch_does_not_match_main_release(self) -> None:
        self.commit_workflow(
            "lambda-release",
            workflow(body="      - run: python tools/lambda_release/release.py\n"),
        )
        base, head = self.change()

        result = self.run_guard(base, head, branch="feature/test")

        self.assertEqual(result.returncode, 0)
        self.assertIn("MERGE_IS_RELEASE_BOUNDARY=NO", result.stdout)

    def test_supported_star_double_star_and_question_globs_match(self) -> None:
        self.commit_workflow(
            "release",
            workflow(
                branches=("ma?n",),
                paths=("backend/**/?.py",),
                body="      - run: terraform apply saved.tfplan\n",
            ),
        )
        base, head = self.change("backend/a/x.py")

        result = self.run_guard(base, head)

        self.assertEqual(result.returncode, 1)
        self.assertIn("EXTERNAL_MUTATION=TERRAFORM_APPLY", result.stdout)

    def test_multiple_paths_and_workflows_are_reported_deterministically(self) -> None:
        self.commit_workflow("validation", workflow(paths=("docs/**",)))
        self.commit_workflow(
            "release",
            workflow(body="      - run: terraform apply saved.tfplan\n"),
        )
        base = self.repo.head
        self.repo.write("backend/audit-api/query.py", "change\n")
        self.repo.write("docs/readme.md", "change\n")
        head = self.repo.commit_all("multiple changes")

        payload = json.loads(self.run_guard(base, head, output="json").stdout)

        self.assertEqual(payload["result"], "BLOCKED")
        self.assertEqual(len(payload["matches"]), 2)
        self.assertEqual(payload["externalMutations"], ["TERRAFORM_APPLY"])
        self.assertEqual(payload["changedFiles"], sorted(payload["changedFiles"]))

    def test_paths_ignore_excludes_only_ignored_changes(self) -> None:
        self.commit_workflow(
            "release",
            workflow(
                paths=(),
                paths_ignore=("docs/**",),
                body="      - run: terraform apply saved.tfplan\n",
            ),
        )
        base, head = self.change("docs/readme.md")

        result = self.run_guard(base, head)

        self.assertEqual(result.returncode, 0)
        self.assertIn("MATCHED_WORKFLOW_COUNT=0", result.stdout)

    def test_validation_only_workflow_passes(self) -> None:
        self.commit_workflow("ci", workflow(body="      - run: python -m unittest\n"))
        base, head = self.change()

        result = self.run_guard(base, head)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("MATCHED_WORKFLOW_COUNT=1", result.stdout)
        self.assertIn("EXTERNAL_MUTATION=NONE", result.stdout)
        self.assertIn("AUTHORIZATION_GRANTED=no", result.stdout)

    def test_known_aws_mutation_is_blocked(self) -> None:
        body = """      - uses: aws-actions/configure-aws-credentials@v6
      - run: aws dynamodb put-item --table-name example
"""
        self.commit_workflow("aws-write", workflow(body=body))
        base, head = self.change()

        result = self.run_guard(base, head)

        self.assertEqual(result.returncode, 1)
        self.assertIn("EXTERNAL_MUTATION=AWS_MUTATION", result.stdout)

    def test_terraform_and_deploy_signatures_are_known(self) -> None:
        body = """      - run: terraform apply saved.tfplan
      - run: sam deploy
"""
        self.commit_workflow("deploy", workflow(body=body))
        base, head = self.change()

        payload = json.loads(self.run_guard(base, head, output="json").stdout)

        self.assertEqual(
            payload["externalMutations"],
            ["AWS_INFRASTRUCTURE_DEPLOY", "TERRAFORM_APPLY"],
        )
        self.assertTrue(payload["mergeIsReleaseBoundary"])

    def test_unknown_potential_mutation_fails_conservatively(self) -> None:
        body = """      - uses: aws-actions/configure-aws-credentials@v6
      - run: python tools/opaque_operation.py
"""
        self.commit_workflow("unknown", workflow(body=body))
        base, head = self.change()

        result = self.run_guard(base, head)

        self.assertEqual(result.returncode, 1)
        self.assertIn("EXTERNAL_MUTATION=UNKNOWN_EXTERNAL_MUTATION", result.stdout)
        self.assertIn("MERGE_IS_RELEASE_BOUNDARY=YES", result.stdout)

    def test_read_only_aws_identity_workflow_passes(self) -> None:
        body = """      - uses: aws-actions/configure-aws-credentials@v6
      - run: aws sts get-caller-identity
"""
        self.commit_workflow("identity", workflow(paths=(), body=body))
        base, head = self.change()

        result = self.run_guard(base, head)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("EXTERNAL_MUTATION=NONE", result.stdout)

    def test_malformed_workflow_is_inconclusive(self) -> None:
        self.commit_workflow("malformed", "name: Broken\non: [push\n")
        base, head = self.change()

        result = self.run_guard(base, head)

        self.assertEqual(result.returncode, 2)
        self.assertIn("MERGE_SIDE_EFFECT_GUARD=INCONCLUSIVE", result.stdout)
        self.assertIn("MERGE_IS_RELEASE_BOUNDARY=YES", result.stdout)

    def test_output_is_deterministic_and_json_is_valid(self) -> None:
        self.commit_workflow("ci", workflow())
        base, head = self.change()

        first = self.run_guard(base, head, output="json")
        second = self.run_guard(base, head, output="json")
        payload = json.loads(first.stdout)

        self.assertEqual(first.returncode, 0)
        self.assertEqual(first.stdout, second.stdout)
        self.assertFalse(payload["authorizationGranted"])
        self.assertFalse(payload["mergeIsReleaseBoundary"])

    def test_guard_reads_workflow_from_head_not_dirty_worktree(self) -> None:
        self.commit_workflow("ci", workflow())
        base, head = self.change()
        self.repo.write(
            ".github/workflows/ci.yml",
            workflow(body="      - run: terraform apply dirty.tfplan\n"),
        )

        result = self.run_guard(base, head)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("EXTERNAL_MUTATION=NONE", result.stdout)

    def test_guard_does_not_mutate_repository(self) -> None:
        self.commit_workflow("ci", workflow())
        base, head = self.change()
        self.repo.write("local-only.txt", "local\n")
        before = self.repo.snapshot()

        result = self.run_guard(base, head)
        after = self.repo.snapshot()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, after)

    def test_invalid_base_is_inconclusive(self) -> None:
        result = self.run_guard("missing", self.repo.head)

        self.assertEqual(result.returncode, 2)
        self.assertIn("ERROR=base_missing", result.stdout)


class GuardSourceTests(unittest.TestCase):
    def test_shell_guard_is_executable(self) -> None:
        self.assertTrue(os.access(PR_HISTORY_GUARD, os.X_OK))

    def test_shell_guard_syntax(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(PR_HISTORY_GUARD)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

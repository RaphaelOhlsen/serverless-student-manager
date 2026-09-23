from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = PROJECT_ROOT / "scripts" / "agentic-preflight.sh"
SCOPE_CHECK = PROJECT_ROOT / "scripts" / "agentic-scope-check.sh"
STAGING_CHECK = PROJECT_ROOT / "scripts" / "agentic-staging-check.sh"


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
        self.git("add", "AGENTS.md", "README.md")
        self.git("commit", "-m", "initial")
        self.base = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("remote", "add", "origin", ".")
        self.git("update-ref", "refs/remotes/origin/main", self.base)
        self.git("switch", "-c", "feature/test")

    def close(self) -> None:
        self._temporary_directory.cleanup()

    def git(
        self,
        *arguments: str,
        input_text: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.root,
            input=input_text,
            text=True,
            capture_output=True,
            check=check,
            env={**os.environ, "LC_ALL": "C"},
        )

    @property
    def branch(self) -> str:
        return self.git("branch", "--show-current").stdout.strip()

    @property
    def head(self) -> str:
        return self.git("rev-parse", "HEAD").stdout.strip()

    def write(self, relative_path: str, content: str | bytes) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")

    def commit_all(self, message: str = "change") -> str:
        self.git("add", "--all")
        self.git("commit", "-m", message)
        return self.head

    def run_guard(
        self, script: Path, *arguments: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(script), *arguments],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "LC_ALL": "C"},
        )

    def semantic_snapshot(
        self,
    ) -> tuple[str, str, bytes, dict[str, str], tuple[tuple[str, str], ...]]:
        head = self.head
        index_path_value = self.git("rev-parse", "--git-path", "index").stdout.strip()
        index_path = Path(index_path_value)
        if not index_path.is_absolute():
            index_path = self.root / index_path
        index_digest = hashlib.sha256(index_path.read_bytes()).hexdigest()
        status = subprocess.run(
            ["git", "status", "--porcelain=v2", "-z"],
            cwd=self.root,
            capture_output=True,
            check=True,
            env={**os.environ, "LC_ALL": "C", "GIT_OPTIONAL_LOCKS": "0"},
        ).stdout
        files: dict[str, str] = {}
        for path in sorted(self.root.rglob("*")):
            if path.is_file() and ".git" not in path.parts:
                files[str(path.relative_to(self.root))] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
        git_directory_value = self.git("rev-parse", "--git-dir").stdout.strip()
        git_directory = Path(git_directory_value)
        if not git_directory.is_absolute():
            git_directory = self.root / git_directory
        objects_root = git_directory / "objects"
        objects = tuple(
            (
                str(path.relative_to(objects_root)),
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            for path in sorted(objects_root.rglob("*"))
            if path.is_file()
        )
        return head, index_digest, status, files, objects


class GitGuardTestCase(unittest.TestCase):
    repo: TemporaryGitRepository

    def setUp(self) -> None:
        self.repo = TemporaryGitRepository()

    def tearDown(self) -> None:
        self.repo.close()

    def scope_arguments(self, *allowed: str) -> list[str]:
        arguments = [
            "--expected-branch",
            self.repo.branch,
            "--expected-head",
            self.repo.head,
            "--base",
            self.repo.base,
        ]
        for path in allowed:
            arguments.extend(("--allow-file", path))
        return arguments

    def staging_arguments(self, *allowed: str) -> list[str]:
        arguments = [
            "--expected-branch",
            self.repo.branch,
            "--expected-head",
            self.repo.head,
        ]
        for path in allowed:
            arguments.extend(("--allow-file", path))
        return arguments


class PreflightTests(GitGuardTestCase):
    def test_legacy_invocation_passes_on_feature_branch(self) -> None:
        result = self.repo.run_guard(PREFLIGHT)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("MODE=implementation", result.stdout)
        self.assertIn("PREFLIGHT_RESULT=PASS", result.stdout)

    def test_legacy_read_only_invocation_passes_on_main(self) -> None:
        self.repo.git("switch", "main")

        result = self.repo.run_guard(PREFLIGHT, "--read-only")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("MODE=read-only", result.stdout)

    def test_implementation_on_main_fails(self) -> None:
        self.repo.git("switch", "main")

        result = self.repo.run_guard(PREFLIGHT)

        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR=implementation_on_main", result.stdout)

    def test_expected_state_and_json_output_pass(self) -> None:
        result = self.repo.run_guard(
            PREFLIGHT,
            "--expected-branch",
            self.repo.branch,
            "--expected-head",
            self.repo.head,
            "--base",
            self.repo.base,
            "--format",
            "json",
        )

        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["result"], "PASS")
        self.assertEqual(payload["base"]["isAncestor"], "yes")

    def test_expected_branch_mismatch_fails_with_valid_json(self) -> None:
        result = self.repo.run_guard(
            PREFLIGHT,
            "--expected-branch",
            "feature/other",
            "--format",
            "json",
        )

        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected_branch_mismatch", payload["errors"])

    def test_expected_head_mismatch_fails(self) -> None:
        result = self.repo.run_guard(
            PREFLIGHT,
            "--expected-head",
            "0" * 40,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR=expected_head_mismatch", result.stdout)

    def test_explicit_unrelated_base_fails(self) -> None:
        empty_tree = self.repo.git("mktree", input_text="").stdout.strip()
        unrelated = self.repo.git(
            "commit-tree", empty_tree, "-m", "unrelated"
        ).stdout.strip()

        result = self.repo.run_guard(PREFLIGHT, "--base", unrelated)

        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR=base_not_ancestor", result.stdout)

    def test_strict_untracked_rejects_other_but_allows_checkpoints(self) -> None:
        self.repo.write("prompt_inicio_dia.txt", "checkpoint\n")
        checkpoint_only = self.repo.run_guard(PREFLIGHT, "--strict-untracked")
        self.repo.write("unexpected.txt", "unexpected\n")
        with_other = self.repo.run_guard(PREFLIGHT, "--strict-untracked")

        self.assertEqual(checkpoint_only.returncode, 0, checkpoint_only.stdout)
        self.assertEqual(with_other.returncode, 1)
        self.assertIn("ERROR=strict_untracked_violation", with_other.stdout)

    def test_tracked_checkpoint_fails(self) -> None:
        self.repo.write("prompt_inicio_dia.txt", "checkpoint\n")
        self.repo.git("add", "prompt_inicio_dia.txt")

        result = self.repo.run_guard(PREFLIGHT)

        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR=checkpoint_tracked:prompt_inicio_dia.txt", result.stdout)

    def test_invalid_format_is_usage_error(self) -> None:
        result = self.repo.run_guard(PREFLIGHT, "--format", "yaml")

        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage:", result.stderr)

    def test_duplicate_option_is_usage_error(self) -> None:
        result = self.repo.run_guard(PREFLIGHT, "--read-only", "--read-only")

        self.assertEqual(result.returncode, 2)

    def test_preflight_does_not_mutate_repository(self) -> None:
        self.repo.write("untracked.txt", "content\n")
        before = self.repo.semantic_snapshot()

        result = self.repo.run_guard(PREFLIGHT)
        after = self.repo.semantic_snapshot()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, after)


class ScopeCheckTests(GitGuardTestCase):
    def test_clean_scope_passes_with_unused_allow_entry(self) -> None:
        result = self.repo.run_guard(
            SCOPE_CHECK, *self.scope_arguments("planned.txt")
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("UNUSED_ALLOWED_FILE=planned.txt", result.stdout)
        self.assertIn("SCOPE_RESULT=PASS", result.stdout)

    def test_staged_unstaged_and_untracked_allowed_files_pass(self) -> None:
        self.repo.write("staged.txt", "staged\n")
        self.repo.git("add", "staged.txt")
        self.repo.write("README.md", "unstaged\n")
        self.repo.write("untracked.txt", "untracked\n")

        result = self.repo.run_guard(
            SCOPE_CHECK,
            *self.scope_arguments("staged.txt", "README.md", "untracked.txt"),
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("STAGED_FILES_COUNT=1", result.stdout)
        self.assertIn("UNSTAGED_FILES_COUNT=1", result.stdout)
        self.assertIn("UNTRACKED_FILES_COUNT=1", result.stdout)

    def test_out_of_scope_file_fails(self) -> None:
        self.repo.write("outside.txt", "outside\n")

        result = self.repo.run_guard(
            SCOPE_CHECK, *self.scope_arguments("inside.txt")
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("OUT_OF_SCOPE_FILE=outside.txt", result.stdout)

    def test_committed_diff_from_base_is_checked(self) -> None:
        self.repo.write("committed.txt", "committed\n")
        self.repo.commit_all()

        result = self.repo.run_guard(
            SCOPE_CHECK, *self.scope_arguments("committed.txt")
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("COMMITTED_FILES_COUNT=1", result.stdout)

    def test_untracked_checkpoint_is_allowed(self) -> None:
        self.repo.write("prompt_inicio_dia copy.txt", "checkpoint\n")

        result = self.repo.run_guard(
            SCOPE_CHECK, *self.scope_arguments("planned.txt")
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CHECKPOINT_FILE=prompt_inicio_dia copy.txt", result.stdout)

    def test_staged_checkpoint_fails(self) -> None:
        self.repo.write("prompt_inicio_dia.txt", "checkpoint\n")
        self.repo.git("add", "prompt_inicio_dia.txt")

        result = self.repo.run_guard(
            SCOPE_CHECK, *self.scope_arguments("prompt_inicio_dia.txt")
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("checkpoint", result.stdout.lower())

    def test_untracked_whitespace_error_fails(self) -> None:
        self.repo.write("new.txt", "trailing whitespace   \n")

        result = self.repo.run_guard(
            SCOPE_CHECK, *self.scope_arguments("new.txt")
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR=untracked_diff_whitespace:new.txt", result.stdout)

    def test_unstaged_whitespace_error_fails(self) -> None:
        self.repo.write("README.md", "trailing whitespace   \n")

        result = self.repo.run_guard(
            SCOPE_CHECK, *self.scope_arguments("README.md")
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR=unstaged_diff_whitespace", result.stdout)

    def test_rename_requires_source_and_destination(self) -> None:
        self.repo.git("mv", "README.md", "renamed.md")

        result = self.repo.run_guard(
            SCOPE_CHECK, *self.scope_arguments("renamed.md")
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("OUT_OF_SCOPE_FILE=README.md", result.stdout)

    def test_paths_with_spaces_are_supported(self) -> None:
        self.repo.write("directory/file with spaces.txt", "content\n")

        result = self.repo.run_guard(
            SCOPE_CHECK,
            *self.scope_arguments("directory/file with spaces.txt"),
            "--format",
            "json",
        )

        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("directory/file with spaces.txt", payload["changes"]["untracked"])

    def test_expected_head_mismatch_fails(self) -> None:
        arguments = self.scope_arguments("planned.txt")
        arguments[3] = "0" * 40

        result = self.repo.run_guard(SCOPE_CHECK, *arguments)

        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR=expected_head_mismatch", result.stdout)

    def test_missing_allowlist_is_usage_error(self) -> None:
        result = self.repo.run_guard(
            SCOPE_CHECK,
            "--expected-branch",
            self.repo.branch,
            "--expected-head",
            self.repo.head,
            "--base",
            self.repo.base,
        )

        self.assertEqual(result.returncode, 2)

    def test_missing_base_object_fails_closed(self) -> None:
        arguments = self.scope_arguments("planned.txt")
        arguments[5] = "0" * 40

        result = self.repo.run_guard(SCOPE_CHECK, *arguments)

        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR=base_missing", result.stdout)

    def test_scope_check_does_not_mutate_repository(self) -> None:
        self.repo.write("new.txt", "content\n")
        before = self.repo.semantic_snapshot()

        result = self.repo.run_guard(
            SCOPE_CHECK, *self.scope_arguments("new.txt")
        )
        after = self.repo.semantic_snapshot()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, after)


class StagingCheckTests(GitGuardTestCase):
    def stage_file(self, path: str = "change.txt", content: str | bytes = "change\n") -> None:
        self.repo.write(path, content)
        self.repo.git("add", "--", path)

    def staged_hash(self, output: str) -> str:
        for line in output.splitlines():
            if line.startswith("STAGED_DIFF_SHA256="):
                return line.split("=", 1)[1]
        self.fail("staged diff hash was not emitted")

    def test_allowed_staged_file_passes_and_emits_hash(self) -> None:
        self.stage_file()

        result = self.repo.run_guard(
            STAGING_CHECK, *self.staging_arguments("change.txt")
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(self.staged_hash(result.stdout), r"^[0-9a-f]{64}$")
        self.assertIn("AUTHORIZATION_GRANTED=no", result.stdout)

    def test_hash_is_deterministic_and_expected_hash_can_be_enforced(self) -> None:
        self.stage_file()
        first = self.repo.run_guard(
            STAGING_CHECK, *self.staging_arguments("change.txt")
        )
        second = self.repo.run_guard(
            STAGING_CHECK, *self.staging_arguments("change.txt")
        )
        digest = self.staged_hash(first.stdout)
        enforced = self.repo.run_guard(
            STAGING_CHECK,
            *self.staging_arguments("change.txt"),
            "--expected-diff-sha256",
            digest,
        )

        self.assertEqual(first.returncode, 0, first.stdout)
        self.assertEqual(second.returncode, 0, second.stdout)
        self.assertEqual(digest, self.staged_hash(second.stdout))
        self.assertEqual(enforced.returncode, 0, enforced.stdout)

    def test_expected_hash_mismatch_fails(self) -> None:
        self.stage_file()

        result = self.repo.run_guard(
            STAGING_CHECK,
            *self.staging_arguments("change.txt"),
            "--expected-diff-sha256",
            "0" * 64,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR=expected_diff_sha256_mismatch", result.stdout)

    def test_hash_changes_when_staged_diff_changes(self) -> None:
        self.stage_file(content="first\n")
        first = self.repo.run_guard(
            STAGING_CHECK, *self.staging_arguments("change.txt")
        )
        self.repo.write("change.txt", "second\n")
        self.repo.git("add", "change.txt")
        second = self.repo.run_guard(
            STAGING_CHECK, *self.staging_arguments("change.txt")
        )

        self.assertNotEqual(self.staged_hash(first.stdout), self.staged_hash(second.stdout))

    def test_unauthorized_staged_file_fails(self) -> None:
        self.stage_file("outside.txt")

        result = self.repo.run_guard(
            STAGING_CHECK, *self.staging_arguments("inside.txt")
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("OUT_OF_SCOPE_FILE=outside.txt", result.stdout)

    def test_staged_checkpoint_fails_even_when_allowlisted(self) -> None:
        self.stage_file("prompt_inicio_dia.txt", "checkpoint\n")

        result = self.repo.run_guard(
            STAGING_CHECK, *self.staging_arguments("prompt_inicio_dia.txt")
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR=checkpoint_staged:prompt_inicio_dia.txt", result.stdout)

    def test_empty_staging_area_fails(self) -> None:
        result = self.repo.run_guard(
            STAGING_CHECK, *self.staging_arguments("planned.txt")
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR=empty_staging_area", result.stdout)

    def test_staged_whitespace_error_fails(self) -> None:
        self.stage_file(content="trailing whitespace   \n")

        result = self.repo.run_guard(
            STAGING_CHECK, *self.staging_arguments("change.txt")
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR=staged_diff_whitespace", result.stdout)

    def test_secret_finding_is_sanitized(self) -> None:
        fake_secret = "ASIA" + "A" * 16
        self.stage_file(content=f"credential={fake_secret}\n")

        result = self.repo.run_guard(
            STAGING_CHECK, *self.staging_arguments("change.txt")
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("SECRET_FINDING_RULE=aws_access_key_id", result.stdout)
        self.assertNotIn(fake_secret, result.stdout)
        self.assertNotIn(fake_secret, result.stderr)

    def test_prohibited_artifact_name_fails(self) -> None:
        self.stage_file(".env.local", "placeholder\n")

        result = self.repo.run_guard(
            STAGING_CHECK, *self.staging_arguments(".env.local")
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("ARTIFACT_FINDING_RULE=environment_file", result.stdout)

    def test_binary_file_is_reported_as_not_inspectable(self) -> None:
        self.stage_file("asset.bin", b"\x00\x01\x02")

        result = self.repo.run_guard(
            STAGING_CHECK, *self.staging_arguments("asset.bin")
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("BINARY_FILE=asset.bin INSPECTION=NOT_INSPECTABLE", result.stdout)

    def test_blank_text_file_is_not_reported_as_binary(self) -> None:
        self.stage_file("blank.txt", "\n\n")

        result = self.repo.run_guard(
            STAGING_CHECK, *self.staging_arguments("blank.txt")
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("BINARY_FILE=", result.stdout)

    def test_json_pass_output_is_valid(self) -> None:
        self.stage_file()

        result = self.repo.run_guard(
            STAGING_CHECK,
            *self.staging_arguments("change.txt"),
            "--format",
            "json",
        )

        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["result"], "PASS")
        self.assertFalse(payload["authorizationGranted"])
        self.assertEqual(payload["indexSha256Before"], payload["indexSha256After"])

    def test_json_failure_output_is_valid_and_sanitized(self) -> None:
        fake_secret = "ghp_" + "A" * 24
        self.stage_file(content=f"token={fake_secret}\n")

        result = self.repo.run_guard(
            STAGING_CHECK,
            *self.staging_arguments("change.txt"),
            "--format",
            "json",
        )

        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(payload["result"], "FAIL")
        self.assertEqual(payload["secretFindings"][0]["rule"], "github_token")
        self.assertNotIn(fake_secret, result.stdout)

    def test_worktree_secret_after_safe_stage_is_not_scanned_as_staged(self) -> None:
        self.stage_file(content="safe staged content\n")
        fake_secret = "ASIA" + "B" * 16
        self.repo.write("change.txt", f"unstaged={fake_secret}\n")

        result = self.repo.run_guard(
            STAGING_CHECK, *self.staging_arguments("change.txt")
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn(fake_secret, result.stdout)

    def test_rename_requires_source_and_destination(self) -> None:
        self.repo.git("mv", "README.md", "renamed.md")

        result = self.repo.run_guard(
            STAGING_CHECK, *self.staging_arguments("renamed.md")
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("OUT_OF_SCOPE_FILE=README.md", result.stdout)

    def test_staging_check_does_not_mutate_repository(self) -> None:
        self.stage_file()
        before = self.repo.semantic_snapshot()

        result = self.repo.run_guard(
            STAGING_CHECK, *self.staging_arguments("change.txt")
        )
        after = self.repo.semantic_snapshot()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, after)

    def test_invalid_expected_hash_is_usage_error(self) -> None:
        self.stage_file()

        result = self.repo.run_guard(
            STAGING_CHECK,
            *self.staging_arguments("change.txt"),
            "--expected-diff-sha256",
            "not-a-hash",
        )

        self.assertEqual(result.returncode, 2)


class SourceTreeTests(unittest.TestCase):
    def test_expected_scripts_are_executable(self) -> None:
        for script in (PREFLIGHT, SCOPE_CHECK, STAGING_CHECK):
            with self.subTest(script=script.name):
                self.assertTrue(os.access(script, os.X_OK))

    def test_shell_syntax(self) -> None:
        result = subprocess.run(
            [
                "bash",
                "-n",
                str(PROJECT_ROOT / "scripts" / "lib" / "agentic-common.sh"),
                str(PREFLIGHT),
                str(SCOPE_CHECK),
                str(STAGING_CHECK),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(PROJECT_ROOT / "scripts" / "tests" / "__pycache__", ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

import zipfile
from pathlib import Path

import pytest

from tools.lambda_release.build_artifact import (
    FIXED_ZIP_TIMESTAMP,
    build_artifact,
    write_deterministic_zip,
)


def test_deterministic_zip_excludes_non_runtime_files(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "package").mkdir(parents=True)
    (source / "package/app.py").write_text("handler = True\n")
    (source / "tests").mkdir()
    (source / "tests/test_app.py").write_text("test = True\n")
    (source / "__pycache__").mkdir()
    (source / "__pycache__/app.pyc").write_bytes(b"bytecode")
    (source / ".pytest_cache").mkdir()
    (source / ".pytest_cache/state").write_text("cache\n")
    (source / ".mypy_cache").mkdir()
    (source / ".mypy_cache/state").write_text("cache\n")
    (source / ".ruff_cache").mkdir()
    (source / ".ruff_cache/state").write_text("cache\n")
    (source / ".env.local").write_text("SECRET=value\n")
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    write_deterministic_zip(source, first)
    write_deterministic_zip(source, second)
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == ["package/app.py"]
        assert archive.getinfo("package/app.py").date_time == FIXED_ZIP_TIMESTAMP


@pytest.mark.parametrize(
    ("api", "package_name"),
    [("students-api", "students_api"), ("users-api", "users_api")],
)
def test_build_uses_release_lock_and_packages_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, api: str, package_name: str
) -> None:
    repository = tmp_path / "repository"
    api_root = repository / "backend" / api
    (api_root / "app" / package_name).mkdir(parents=True)
    (api_root / "app" / package_name / "app.py").write_text("handler = True\n")
    lock_file = repository / "tools/lambda_release/requirements" / f"{api}.txt"
    lock_file.parent.mkdir(parents=True)
    lock_file.write_text("dependency==1.0\n")
    output = tmp_path / f"{api}.zip"

    def fake_run(command: list[str], *, check: bool) -> None:
        assert check is True
        assert str(lock_file) in command
        target = Path(command[command.index("--target") + 1])
        (target / "dependency.py").write_text("installed = True\n")

    monkeypatch.setattr("tools.lambda_release.build_artifact.subprocess.run", fake_run)
    build_artifact(api, output, repository)

    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == ["dependency.py", f"{package_name}/app.py"]


def test_build_audit_api_uses_release_lock_and_packages_only_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    api_root = repository / "backend/audit-api"
    (api_root / "app/audit_api").mkdir(parents=True)
    (api_root / "app/audit_api/app.py").write_text("handler = True\n")
    (api_root / "app/audit_api/__pycache__").mkdir()
    (api_root / "app/audit_api/__pycache__/app.pyc").write_bytes(b"bytecode")
    (api_root / "app/audit_api/.env.test").write_text("SECRET=value\n")
    (api_root / "app/tests").mkdir()
    (api_root / "app/tests/test_app.py").write_text("test = True\n")
    lock_file = repository / "tools/lambda_release/requirements/audit-api.txt"
    lock_file.parent.mkdir(parents=True)
    lock_file.write_text("dependency==1.0\n")
    output = tmp_path / "audit.zip"

    def fake_run(command: list[str], *, check: bool) -> None:
        assert check is True
        assert str(lock_file) in command
        target = Path(command[command.index("--target") + 1])
        (target / "dependency.py").write_text("installed = True\n")

    monkeypatch.setattr("tools.lambda_release.build_artifact.subprocess.run", fake_run)
    build_artifact("audit-api", output, repository)

    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == ["audit_api/app.py", "dependency.py"]

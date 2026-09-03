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
    (source / ".env.local").write_text("SECRET=value\n")
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    write_deterministic_zip(source, first)
    write_deterministic_zip(source, second)
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == ["package/app.py"]
        assert archive.getinfo("package/app.py").date_time == FIXED_ZIP_TIMESTAMP


def test_build_uses_release_lock_and_packages_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    api_root = repository / "backend/users-api"
    (api_root / "app/users_api").mkdir(parents=True)
    (api_root / "app/users_api/app.py").write_text("handler = True\n")
    lock_file = repository / "tools/lambda_release/requirements/users-api.txt"
    lock_file.parent.mkdir(parents=True)
    lock_file.write_text("dependency==1.0\n")
    output = tmp_path / "users.zip"

    def fake_run(command: list[str], *, check: bool) -> None:
        assert check is True
        assert str(lock_file) in command
        target = Path(command[command.index("--target") + 1])
        (target / "dependency.py").write_text("installed = True\n")

    monkeypatch.setattr("tools.lambda_release.build_artifact.subprocess.run", fake_run)
    build_artifact("users-api", output, repository)

    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == ["dependency.py", "users_api/app.py"]

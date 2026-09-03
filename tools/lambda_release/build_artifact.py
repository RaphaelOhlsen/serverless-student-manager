from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

SUPPORTED_APIS = {"students-api", "users-api"}
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
EXCLUDED_PARTS = {"__pycache__", "tests", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def _is_included(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if any(part.startswith(".env") for part in relative.parts):
        return False
    return path.is_file() and path.suffix != ".pyc"


def write_deterministic_zip(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source.rglob("*"), key=lambda item: item.as_posix()):
            if not _is_included(path, source):
                continue
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(relative, FIXED_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(
                info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9
            )


def build_artifact(api: str, output: Path, repository_root: Path) -> None:
    if api not in SUPPORTED_APIS:
        raise ValueError("unsupported API")
    api_root = repository_root / "backend" / api
    app_root = api_root / "app"
    lock_file = repository_root / "tools" / "lambda_release" / "requirements" / f"{api}.txt"
    package_name = api.replace("-", "_")
    if not (app_root / package_name / "app.py").is_file() or not lock_file.is_file():
        raise ValueError("release inputs are incomplete")

    with tempfile.TemporaryDirectory(prefix=f"{api}-release-") as temporary:
        build_root = Path(temporary)
        subprocess.run(
            [
                os.fspath(Path(sys.executable)),
                "-m",
                "pip",
                "install",
                "--requirement",
                os.fspath(lock_file),
                "--target",
                os.fspath(build_root),
                "--no-compile",
                "--disable-pip-version-check",
            ],
            check=True,
        )
        shutil.copytree(app_root, build_root, dirs_exist_ok=True)
        write_deterministic_zip(build_root, output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", required=True, choices=sorted(SUPPORTED_APIS))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repository_root = Path(__file__).resolve().parents[2]
    build_artifact(args.api, args.output.resolve(), repository_root)


if __name__ == "__main__":
    main()

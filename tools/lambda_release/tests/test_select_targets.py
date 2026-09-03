import pytest

from tools.lambda_release.select_targets import select_targets


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        (["backend/students-api/app/students_api/app.py"], ["students-api"]),
        (["backend/users-api/app/users_api/app.py"], ["users-api"]),
        (
            ["backend/users-api/app.py", "backend/students-api/app.py"],
            ["students-api", "users-api"],
        ),
        (["tools/lambda_release/requirements/users-api.txt"], []),
        (["tools/lambda_release/release.py"], []),
        ([".github/workflows/lambda-release.yml"], []),
        (["frontend/src/App.tsx"], []),
    ],
)
def test_select_targets(paths: list[str], expected: list[str]) -> None:
    assert select_targets(paths) == expected
